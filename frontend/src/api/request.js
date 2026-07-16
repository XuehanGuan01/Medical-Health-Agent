// HTTP 请求封装
const TIMEOUT = 120000

let _baseURL = localStorage.getItem('baseURL') || ''

export const setBaseURL = (url) => { _baseURL = url; localStorage.setItem('baseURL', url) }
export const getBaseURL = () => _baseURL

const request = async (url, options = {}) => {
  const method = options.method || 'GET'
  let fullURL = _baseURL + url

  // GET/DELETE: data → URL query string
  if (options.data && (method === 'GET' || method === 'DELETE')) {
    const qs = new URLSearchParams(options.data).toString()
    fullURL += (url.includes('?') ? '&' : '?') + qs
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT)

  try {
    const hasBody = method !== 'GET' && method !== 'DELETE' && options.data
    const headers = { ...options.header }
    if (hasBody) headers['Content-Type'] = 'application/json'

    const res = await fetch(fullURL, {
      method,
      headers,
      body: hasBody ? JSON.stringify(options.data) : undefined,
      signal: controller.signal,
    })
    clearTimeout(timer)
    if (!res.ok) {
      showToast(`Error ${res.status}`)
      throw new Error(`HTTP ${res.status}`)
    }
    return await res.json()
  } catch (e) {
    clearTimeout(timer)
    if (e.name === 'AbortError') showToast('请求超时')
    else if (e.message === 'Failed to fetch' || e.name === 'TypeError') showToast('网络不可达')
    throw e
  }
}

const showToast = (msg) => {
  const el = document.createElement('div')
  el.className = 'global-toast'
  el.textContent = msg
  document.body.appendChild(el)
  setTimeout(() => { el.classList.add('fade'); setTimeout(() => el.remove(), 300) }, 2000)
}

export default request
