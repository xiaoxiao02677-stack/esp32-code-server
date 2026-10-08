(async function(){
const img=document.querySelector('img.cap-img');
const c=document.createElement('canvas');
c.width=img.naturalWidth*4;c.height=img.naturalHeight*4;
const ctx=c.getContext('2d');
ctx.drawImage(img,0,0,c.width,c.height);
const d=ctx.getImageData(0,0,c.width,c.height);
const px=d.data;
for(let i=0;i<px.length;i+=4){
  const g=px[i]*0.3+px[i+1]*0.6+px[i+2]*0.1;
  const v=g>140?255:0;
  px[i]=v;px[i+1]=v;px[i+2]=v;
}
ctx.putImageData(d,0,0);
const res=await Tesseract.recognize(c.toDataURL(),'eng',{tessedit_pageseg_mode:'7',tessedit_char_whitelist:'0123456789abcdefghijklmnopqrstuvwxyz'});
return 'CODE:'+((res.data.text||'').replace(/[^0-9a-z]/g,''));
})()
