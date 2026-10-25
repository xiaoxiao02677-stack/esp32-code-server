<script setup>
// 商店专用内联图标集：24x24 / stroke 1.7 / round caps —— 与控制台 emoji 拉开差距
defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 18 }
})

const P = {
  bag: ['M6.2 8.2h11.6l-1.1 11a2 2 0 0 1-2 1.8H9.3a2 2 0 0 1-2-1.8l-1.1-11Z', 'M9.2 8V6.4a2.8 2.8 0 0 1 5.6 0V8'],
  truck: ['M3 7.5h10.5v8.2H3z', 'M13.5 10.6h3.4l3.1 3v2.1h-6.5z', 'M6.8 18.9a1.7 1.7 0 1 0 0-3.4 1.7 1.7 0 0 0 0 3.4Z', 'M17.3 18.9a1.7 1.7 0 1 0 0-3.4 1.7 1.7 0 0 0 0 3.4Z'],
  badge: ['M12 3.2a8.8 8.8 0 1 0 0 17.6 8.8 8.8 0 0 0 0-17.6Z', 'm8.6 12.3 2.3 2.3 4.5-4.7'],
  package: ['M12 3.4 4.4 7.5v9L12 20.6l7.6-4.1v-9L12 3.4Z', 'M4.4 7.5 12 11.6l7.6-4.1', 'M12 11.6v9'],
  user: ['M12 4.8a3.3 3.3 0 1 0 0 6.6 3.3 3.3 0 0 0 0-6.6Z', 'M5.6 19.8c.9-3.2 3.4-4.8 6.4-4.8s5.5 1.6 6.4 4.8'],
  pin: ['M12 21s-6.6-5.3-6.6-10.2a6.6 6.6 0 0 1 13.2 0C18.6 15.7 12 21 12 21Z', 'M12 12.8a2.2 2.2 0 1 0 0-4.4 2.2 2.2 0 0 0 0 4.4Z'],
  search: ['M11 4.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13Z', 'm16.2 16.2 4.3 4.3'],
  clock: ['M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17Z', 'M12 7.8V12l3 2'],
  receipt: ['M7 3.5h10v17l-2.5-1.5-2.5 1.5-2.5-1.5L7 20.5v-17Z', 'M10 8.5h4', 'M10 12h4'],
  spark: ['M12 4.5l1.6 4.3 4.4 1.5-4.4 1.5L12 16l-1.6-4.2-4.4-1.5 4.4-1.5L12 4.5Z'],
  plus: ['M12 5.5v13', 'M5.5 12h13'],
  arrow: ['M4.5 12h15', 'm13 5.5 6.5 6.5L13 18.5'],
  check: ['m5 12.5 4.5 4.5L19 7.5']
}
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path v-for="(d, i) in P[name] || []" :key="i" :d="d" />
  </svg>
</template>
