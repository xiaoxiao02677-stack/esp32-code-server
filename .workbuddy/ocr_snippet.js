(async function(){
  const btn = [...document.querySelectorAll('button')].find(b=>b.textContent.includes('验证码')||b.querySelector('img,canvas'));
  const img = btn ? (btn.querySelector('img')||btn) : null;
  if(!img || !img.src) return 'no captcha img; btn HTML: '+(btn?btn.outerHTML.slice(0,300):'none');
  const c = document.createElement('canvas');
  const scale = 3;
  c.width = (img.naturalWidth||img.width)*scale;
  c.height = (img.naturalHeight||img.height)*scale;
  const ctx = c.getContext('2d');
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, 0, 0, c.width, c.height);
  const dataUrl = c.toDataURL();
  const res = await Tesseract.recognize(dataUrl, 'eng', {tessedit_char_whitelist:'0123456789'});
  return 'OCR_RESULT:'+(res.data.text||'').replace(/\s+/g,'');
})()
