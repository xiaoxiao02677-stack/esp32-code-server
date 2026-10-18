// 本地 Node 复现登录加密（与 api.js 完全相同的调用）
const { sm2 } = require('sm-crypto')
const https = require('https')

function get(url) {
  return new Promise((resolve, reject) => {
    const u = new URL(url)
    const req = https.request({ hostname: u.hostname, port: u.port || 443, path: u.pathname + u.search, rejectUnauthorized: false }, res => {
      let d = ''
      res.on('data', c => d += c)
      res.on('end', () => resolve(JSON.parse(d)))
    })
    req.on('error', reject)
    req.end()
  })
}

async function main() {
  const pub = await get('https://sandyun.top:8001/yuhe/user/pub-config')
  const pk = pub.data.sm2PublicKey
  console.log('pubKey len=', pk.length, 'head=', pk.slice(0, 8))
  // 与 api.js:79 完全一致：原样传 pk
  try {
    const enc = '04' + sm2.doEncrypt('zN6xs' + 'P@ssword123', pk, 1)
    console.log('ENCRYPT_OK len=', enc.length)
    const body = JSON.stringify({ username: 'demo', password: enc, captchaId: 'probe-node' })
    const u = new URL('https://sandyun.top:8001/yuhe/user/login')
    const req = https.request({ hostname: u.hostname, port: 443, path: u.pathname, method: 'POST', rejectUnauthorized: false, headers: { 'Content-Type': 'application/json' } }, res => {
      let d = ''
      res.on('data', c => d += c)
      res.on('end', () => console.log('LOGIN_RESP:', d.slice(0, 120)))
    })
    req.write(body)
    req.end()
  } catch (e) {
    console.log('ENCRYPT_FAIL:', e.message)
  }
}
main()
