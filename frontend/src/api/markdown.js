/**
 * Markdown → HTML 渲染（对齐原型 mdToHtml）
 * 支持: ## ### 标题、**加粗**、- 列表、| 表格、分段、内联代码
 */
export const renderMarkdown = (md) => {
  if (!md) return ''

  // 1. HTML 转义
  let html = md
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // 2. 表格 — 匹配连续的 | 行
  html = html.replace(/((?:\|.*\|[\s\S]*?(?=\n\n|$)))/g, (m) => {
    const rows = m.trim().split('\n').filter(r => r.includes('|'))
    if (rows.length < 2) return m
    let table = '<table>'
    rows.forEach((row, i) => {
      const cells = row.split('|').filter(c => c.trim() !== '')
      const tag = i === 0 ? 'th' : 'td'
      table += '<tr>' + cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join('') + '</tr>'
    })
    table += '</table>'
    return table
  })

  // 3. 标题
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>')

  // 4. 加粗
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')

  // 5. 行内代码
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')

  // 6. 列表项（- 开头）
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>')
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>')

  // 7. 分段（双换行）
  html = html.replace(/\n\n+/g, '</p><p>')
  html = '<p>' + html + '</p>'

  // 8. 修正嵌套错误
  html = html.replace(/<p>\s*<\/p>/g, '')
  html = html.replace(/<p>(<ul>[\s\S]*?<\/ul>)<\/p>/g, '$1')
  html = html.replace(/<p>(<table>[\s\S]*?<\/table>)<\/p>/g, '$1')
  html = html.replace(/<p>(<h[23]>[\s\S]*?<\/h[23]>)<\/p>/g, '$1')

  // 9. 单换行 → <br>（保留列表和表格内的换行）
  html = html.replace(/\n/g, '<br>')
  // 修复 <br> 在块级元素后面的冗余
  html = html.replace(/(<\/h[23]>|<\/ul>|<\/table>|<\/li>)<br>/g, '$1')

  return html
}

export default { renderMarkdown }
