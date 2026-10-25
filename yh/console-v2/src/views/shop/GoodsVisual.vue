<script setup>
// 商品视觉容器：emoji 棚拍化——底光渐变 + 柔和投影 + 玻璃底托 + 微噪点，
// 把"裸 emoji"处理成"产品摄影"的观感（治 AI 味最重的一环）。
// cover 为图片 URL（http(s)/data:/本站相对路径）时渲染 <img> 并 object-fit:cover
// 自适应拉满——任意像素尺寸（过大/过小）都等比缩放裁切铺满容器，无需预处理。
import { computed } from 'vue'
import { coverSrc, isImgCover } from '../../lib/coverImg'

const props = defineProps({
  emoji: { type: String, default: '🛍️' },   // emoji 或图片 URL
  size: { type: Number, default: 64 },     // emoji 字号
  hue: { type: String, default: 'blue' }   // 底光色系：blue | teal | warm | violet
})

const HUES = {
  blue:   ['rgba(27,108,255,.10)', 'rgba(83,146,255,.04)'],
  teal:   ['rgba(55,200,168,.12)', 'rgba(55,200,168,.04)'],
  warm:   ['rgba(255,138,69,.12)', 'rgba(255,180,84,.05)'],
  violet: ['rgba(122,108,255,.10)', 'rgba(160,150,255,.04)']
}

const bg = computed(() => {
  const [a, b] = HUES[props.hue] || HUES.blue
  return `radial-gradient(120% 90% at 50% 8%, ${a}, transparent 58%), radial-gradient(90% 80% at 50% 108%, ${b}, transparent 55%)`
})

const isImg = computed(() => isImgCover(props.emoji))
const imgSrc = computed(() => coverSrc(props.emoji))
</script>

<template>
  <div class="goods-visual" :style="{ background: bg }">
    <template v-if="isImg">
      <img class="gv-img" :src="imgSrc" alt="" loading="lazy" />
    </template>
    <template v-else>
      <span class="gv-shadow" aria-hidden="true"></span>
      <span class="gv-emoji" :style="{ fontSize: size + 'px' }">{{ emoji }}</span>
    </template>
  </div>
</template>

<style scoped>
.goods-visual {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.gv-emoji {
  position: relative;
  z-index: 2;
  line-height: 1;
  filter: drop-shadow(0 14px 18px rgba(27,44,80,.22)) drop-shadow(0 3px 6px rgba(27,44,80,.14));
  transform: translateZ(0);
}
/* 图片封面：自适应拉满（等比缩放裁切，过大过小都铺满） */
.gv-img {
  position: relative;
  z-index: 2;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.gv-shadow {
  position: absolute;
  bottom: 9%;
  left: 50%;
  width: 46%;
  height: 9%;
  transform: translateX(-50%);
  background: radial-gradient(50% 50% at 50% 50%, rgba(27,44,80,.25), transparent 70%);
  filter: blur(3px);
  z-index: 1;
}
/* 细噪点：打破数码平感（仅 emoji 态叠加；图片保持原貌） */
.goods-visual::after {
  content: "";
  position: absolute; inset: 0; z-index: 3; pointer-events: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='120' height='120' filter='url(%23n)' opacity='0.05'/%3E%3C/svg%3E");
  mix-blend-mode: overlay;
}
</style>
