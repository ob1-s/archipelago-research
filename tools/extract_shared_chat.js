#!/usr/bin/env node

/*
 * Read-only decoder for the serialized conversation embedded in a public
 * ChatGPT share page. This intentionally emits derived text/JSON only; it
 * never writes to the workspace.
 */

const url = process.argv[2];
const mode = process.argv[3] || "summary";
const query = process.argv.slice(4).join(" ").trim();

if (!url) {
  console.error("usage: extract_shared_chat.js <share-url> [summary|search|jsonl] [query]");
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

const messages = nodes.filter((node) => node?.message).map(normalized);

if (mode === "jsonl") {
  for (const message of messages) process.stdout.write(`${JSON.stringify(message)}\n`);
} else if (mode === "search") {
  if (!query) throw new Error("search mode requires a query");
  const needle = query.toLocaleLowerCase();
  for (const message of messages) {
    if (message.text.toLocaleLowerCase().includes(needle)) {
      const excerpt = message.text.length > 1200 ? `${message.text.slice(0, 1200)}…` : message.text;
      console.log(JSON.stringify({ ...message, text: excerpt }));
    }
  }
} else if (mode === "summary") {
  const counts = {};
  const contentTypes = {};
  let first = null;
  let last = null;
  for (const message of messages) {
    counts[message.role || "unknown"] = (counts[message.role || "unknown"] || 0) + 1;
    contentTypes[message.content_type || "unknown"] = (contentTypes[message.content_type || "unknown"] || 0) + 1;
    if (message.create_time !== null) {
      first = first === null ? message.create_time : Math.min(first, message.create_time);
      last = last === null ? message.create_time : Math.max(last, message.create_time);
    }
  }
  console.log(JSON.stringify({
    url,
    title: data.title,
    conversation_id: data.conversation_id,
    backing_conversation_id: data.backing_conversation_id,
    current_node: data.current_node,
    node_count: messages.length,
    linear_count: nodes.length,
    role_counts: counts,
    content_type_counts: contentTypes,
    first_create_time: first,
    last_create_time: last,
    public: data.is_public,
  }, null, 2));
} else {
  throw new Error(`unknown mode: ${mode}`);
}
