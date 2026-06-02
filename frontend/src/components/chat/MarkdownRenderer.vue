<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'

// Configure marked with highlight.js for code blocks
marked.setOptions({
  breaks: true,
  gfm: true,
  highlight(code: string, lang: string) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(code, { language: lang }).value
      } catch { /* fallthrough */ }
    }
    return hljs.highlightAuto(code).value
  },
})

const props = defineProps<{
  content: string
  isStreaming?: boolean
}>()

const rendered = computed(() => {
  if (!props.content && props.isStreaming) return ''
  try {
    return marked.parse(props.content || '') as string
  } catch {
    return props.content
  }
})
</script>

<template>
  <div
    class="markdown-body text-sm leading-relaxed"
    :class="{ 'streaming-cursor': isStreaming && !content }"
    v-html="rendered"
  />
</template>

<style scoped>
/* Import highlight.js dark theme for code blocks */
@import 'highlight.js/styles/atom-one-dark.css';

/* Base markdown styles */
.markdown-body :deep(p) { margin: 0.5em 0; }
.markdown-body :deep(p:first-child) { margin-top: 0; }
.markdown-body :deep(p:last-child) { margin-bottom: 0; }

/* Headings */
.markdown-body :deep(h1) { font-size: 1.3em; font-weight: 700; margin: 0.8em 0 0.4em; }
.markdown-body :deep(h2) { font-size: 1.15em; font-weight: 700; margin: 0.7em 0 0.3em; }
.markdown-body :deep(h3) { font-size: 1.05em; font-weight: 600; margin: 0.6em 0 0.2em; }

/* Lists */
.markdown-body :deep(ul),
.markdown-body :deep(ol) { padding-left: 1.5em; margin: 0.4em 0; }
.markdown-body :deep(li) { margin: 0.15em 0; }

/* Inline code */
.markdown-body :deep(code:not(pre code)) {
  background: #f1f5f9;
  color: #e11d48;
  padding: 0.15em 0.4em;
  border-radius: 3px;
  font-size: 0.9em;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
}

/* Code blocks */
.markdown-body :deep(pre) {
  background: #1e293b;
  color: #e2e8f0;
  padding: 0.8em 1em;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.6em 0;
  font-size: 0.85em;
  line-height: 1.5;
}
.markdown-body :deep(pre code) {
  background: none;
  color: inherit;
  padding: 0;
  font-size: inherit;
}

/* Blockquote */
.markdown-body :deep(blockquote) {
  border-left: 3px solid #3b82f6;
  padding-left: 0.8em;
  margin: 0.5em 0;
  color: #64748b;
  font-style: italic;
}

/* Tables */
.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0.5em 0;
  font-size: 0.9em;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #e2e8f0;
  padding: 0.4em 0.7em;
  text-align: left;
}
.markdown-body :deep(th) {
  background: #f8fafc;
  font-weight: 600;
}

/* Links */
.markdown-body :deep(a) {
  color: #3b82f6;
  text-decoration: underline;
}

/* Horizontal rule */
.markdown-body :deep(hr) { border: none; border-top: 1px solid #e2e8f0; margin: 0.8em 0; }

/* Strong / bold */
.markdown-body :deep(strong) { font-weight: 700; }
</style>
