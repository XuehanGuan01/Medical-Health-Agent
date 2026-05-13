// 轻量 Markdown → HTML (仅渲染 **bold**、- 列表、分段)
export const renderMarkdown = (text) => {
  if (!text) return ''
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // 分段：连续空行 → 段落
  html = html.replace(/\n\n+/g, '</p><p>')
  html = '<p>' + html + '</p>'

  // **bold**
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')

  // 行首 - 列表项
  html = html.replace(/<p>- (.*?)<\/p>/g, '<li>$1</li>')
  html = html.replace(/(<li>.*?<\/li>)+/g, '<ul>$&</ul>')

  // 清理空 <p>
  html = html.replace(/<p>\s*<\/p>/g, '')
  // 清理 <li> 外多余的 <p>
  html = html.replace(/<p><li>/g, '<li>').replace(/<\/li><\/p>/g, '</li>')

  return html
}
