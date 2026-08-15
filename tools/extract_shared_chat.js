#!/usr/bin/env node

import { createHash } from "node:crypto";
import { writeFileSync } from "node:fs";

/*
 * Read-only decoder for the serialized conversation embedded in a public
 * ChatGPT share page. This intentionally emits derived text/JSON only; it
 * never writes to the workspace.
 */

const url = process.argv[2];
const mode = process.argv[3] || "summary";
const query = process.argv.slice(4).join(" ").trim();

if (!url) {
  console.error(
    "usage: extract_shared_chat.js <share-url> [summary|audit|search|jsonl|visible-jsonl|materialize-all|materialize-visible] [query-or-output-path]",
  );
  process.exit(2);
}

const html = await (await fetch(url)).text();
const marker = "streamController.enqueue(";
const markerAt = html.indexOf(marker);
if (markerAt < 0) throw new Error("share page did not contain serialized conversation data");

const quoteAt = markerAt + marker.length;
if (html[quoteAt] !== '"') throw new Error("unexpected stream encoding");

let endAt = quoteAt + 1;
let escaped = false;
for (; endAt < html.length; endAt += 1) {
  const char = html[endAt];
  if (escaped) {
    escaped = false;
  } else if (char === "\\") {
    escaped = true;
  } else if (char === '"') {
    break;
  }
}

const stream = JSON.parse(html.slice(quoteAt, endAt + 1));
const table = JSON.parse(stream);
const memo = new Map();
const special = {
  "-1": Number.NaN,
  "-2": Number.POSITIVE_INFINITY,
  "-3": Number.NEGATIVE_INFINITY,
  "-4": -0,
  "-5": undefined,
};

function reference(value) {
  if (typeof value !== "number") return value;
  if (value < 0) return special[String(value)];
  return hydrate(value);
}

function hydrate(index) {
  if (memo.has(index)) return memo.get(index);
  const value = table[index];
  if (value === null || typeof value !== "object") {
    memo.set(index, value);
    return value;
  }

  const output = Array.isArray(value) ? [] : {};
  memo.set(index, output);
  if (Array.isArray(value)) {
    for (const item of value) output.push(reference(item));
  } else {
    for (const [key, item] of Object.entries(value)) {
      const outputKey = key.startsWith("_") ? hydrate(Number(key.slice(1))) : key;
      output[outputKey] = reference(item);
    }
  }
  return output;
}

const root = hydrate(0);
const route = Object.values(root.loaderData || {}).find((value) => value?.serverResponse);
if (!route?.serverResponse?.data) throw new Error("conversation payload was not found");
const data = route.serverResponse.data;
const nodes = data.linear_conversation || Object.values(data.mapping || {});

function parts(message) {
  const content = message?.content;
  if (!content) return [];
  if (Array.isArray(content.parts)) return content.parts.filter((part) => typeof part === "string");
  if (typeof content.text === "string") return [content.text];
  return [];
}

function textOf(node) {
  return parts(node?.message).join("\n");
}

function normalized(node, index) {
  const message = node.message || {};
  return {
    index,
    id: node.id || message.id,
    parent: node.parent,
    children: node.children || [],
    role: message.author?.role || null,
    create_time: message.create_time ?? null,
    status: message.status || null,
    content_type: message.content?.content_type || null,
    text: textOf(node),
    metadata: message.metadata || {},
  };
}

const allNodes = nodes.map(normalized);
// Keep the historical message index stable for source citations while the
// all-node materialization retains the linear-node index. The original
// decoder's JSONL used the ordinal among message-bearing nodes.
const messages = allNodes
  .filter((node) => node.role !== null)
  .map((node, index) => ({ ...node, index }));

// The public share payload contains more than ordinary conversation: system
// messages, hidden model state, tool records, code cells, and redacted
// placeholders. This is intentionally conservative. A visible historical
// conversation row must be a user/assistant text or multimodal-text message,
// not hidden, not a user-system message, and not redacted. Code cells are
// retained in the all-node corpus and audit counts but excluded from the
// ordinary historical corpus because they are operational cells, not ordinary
// prose conversation.
function isVisibleOrdinary(message) {
  return (
    (message.role === "user" || message.role === "assistant") &&
    (message.content_type === "text" || message.content_type === "multimodal_text") &&
    message.metadata?.is_visually_hidden_from_conversation !== true &&
    message.metadata?.is_user_system_message !== true &&
    message.metadata?.is_redacted !== true
  );
}

const visibleMessages = messages.filter(isVisibleOrdinary);

function jsonlText(records) {
  return records.length === 0
    ? ""
    : `${records.map((record) => JSON.stringify(record)).join("\n")}\n`;
}

function sha256(value) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function countBy(records, selector, fallback = "unknown") {
  const counts = {};
  for (const record of records) {
    const key = selector(record) || fallback;
    counts[key] = (counts[key] || 0) + 1;
  }
  return counts;
}

const allCorpusText = jsonlText(allNodes);
const visibleCorpusText = jsonlText(visibleMessages);
const audit = {
  url,
  title: data.title,
  conversation_id: data.conversation_id,
  backing_conversation_id: data.backing_conversation_id,
  current_node: data.current_node,
  public: data.is_public,
  linear_count: nodes.length,
  decoded_node_count: allNodes.length,
  decoded_message_count: messages.length,
  visible_ordinary_message_count: visibleMessages.length,
  role_counts: countBy(messages, (message) => message.role),
  content_type_counts: countBy(messages, (message) => message.content_type),
  visible_role_counts: countBy(visibleMessages, (message) => message.role),
  visible_content_type_counts: countBy(visibleMessages, (message) => message.content_type),
  first_create_time: messages.reduce(
    (value, message) =>
      message.create_time === null ? value : value === null ? message.create_time : Math.min(value, message.create_time),
    null,
  ),
  last_create_time: messages.reduce(
    (value, message) =>
      message.create_time === null ? value : value === null ? message.create_time : Math.max(value, message.create_time),
    null,
  ),
  raw_html_sha256: sha256(html),
  decoder_blob_sha256: sha256(stream),
  decoded_corpus_sha256: sha256(allCorpusText),
  visible_corpus_sha256: sha256(visibleCorpusText),
  visibility_policy: {
    roles: ["user", "assistant"],
    content_types: ["text", "multimodal_text"],
    require_metadata_flag: "is_visually_hidden_from_conversation is not true",
    exclude_metadata_flags: ["is_user_system_message is true", "is_redacted is true"],
    excluded_even_if_not_hidden: ["code", "model_editable_context", "reasoning_recap", "thoughts", "tool/system records"],
  },
};

if (mode === "jsonl") {
  for (const message of messages) process.stdout.write(`${JSON.stringify(message)}\n`);
} else if (mode === "visible-jsonl") {
  process.stdout.write(visibleCorpusText);
} else if (mode === "materialize-all" || mode === "materialize-visible") {
  const outputPath = process.argv[4];
  if (!outputPath) throw new Error(`${mode} requires an explicit output path`);
  writeFileSync(outputPath, mode === "materialize-all" ? allCorpusText : visibleCorpusText, "utf8");
  console.log(JSON.stringify({ ...audit, materialized_path: outputPath, materialized_kind: mode }, null, 2));
} else if (mode === "search") {
  if (!query) throw new Error("search mode requires a query");
  const needle = query.toLocaleLowerCase();
  for (const message of messages) {
    if (message.text.toLocaleLowerCase().includes(needle)) {
      const excerpt = message.text.length > 1200 ? `${message.text.slice(0, 1200)}…` : message.text;
      console.log(JSON.stringify({ ...message, text: excerpt }));
    }
  }
} else if (mode === "summary" || mode === "audit") {
  const summary = {
    ...audit,
    node_count: messages.length,
  };
  console.log(JSON.stringify(summary, null, 2));
} else {
  throw new Error(`unknown mode: ${mode}`);
}
