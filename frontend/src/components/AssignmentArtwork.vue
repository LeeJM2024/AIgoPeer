<script setup>
import { computed } from 'vue'
import { assignmentArt } from '../presentation/assignments'
const props = defineProps({
  assignment: { type: Object, default: () => ({}) },
  kind: { type: String, default: '' }
})
const visual = computed(() => props.kind || assignmentArt(props.assignment))
const labels = {
  merge: '归并排序主题插画：拆分数组，再合并为有序数组',
  graph: '图算法主题插画：路径与节点',
  dp: '动态规划主题插画：从状态表中选取最优值',
  tree: '树与递归主题插画：从父节点展开子问题',
  sum: '整数求和主题插画：输入 a 和 b，输出 a 加 b',
  lesson: '微课项目主题插画：代码、算法结构与讲解材料',
  code: '代码主题插画：输入、计算与输出'
}
</script>
<template>
  <svg
    class="assignment-artwork"
    viewBox="0 0 600 400"
    role="img"
    :aria-label="labels[visual] || labels.code"
  >
    <g v-if="visual === 'merge'">
      <g class="art-lines" fill="none" stroke-width="4" stroke-linecap="round">
        <path
          d="M240 104v26q0 18-18 18H128q-18 0-18 18v17M360 104v26q0 18 18 18h94q18 0 18 18v17M110 240v30q0 18 18 18h112q20 0 20 20v5M490 240v30q0 18-18 18H360q-20 0-20 20v5"
        />
      </g>
      <g class="art-paper">
        <rect x="152" y="40" width="296" height="60" rx="14" />
      </g>
      <g class="art-accent">
        <rect
          x="36"
          y="182"
          width="148"
          height="60"
          rx="14"
          transform="rotate(-4 110 212)"
        />
        <rect
          x="416"
          y="182"
          width="148"
          height="60"
          rx="14"
          transform="rotate(4 490 212)"
        />
      </g>
      <rect class="art-dark" x="152" y="316" width="296" height="60" rx="14" />
      <g class="art-ink" font-size="35" font-weight="650" text-anchor="middle">
        <text
          v-for="(value, index) in [8, 3, 5, 1]"
          :key="index"
          :x="189 + index * 74"
          y="82"
        >
          {{ value }}
        </text>
      </g>
      <g
        class="art-white"
        font-size="35"
        font-weight="600"
        text-anchor="middle"
      >
        <text x="73" y="224">3</text>
        <text x="147" y="224">8</text>
        <text x="453" y="224">1</text>
        <text x="527" y="224">5</text>
        <text
          v-for="(value, index) in [1, 3, 5, 8]"
          :key="index"
          :x="189 + index * 74"
          y="358"
        >
          {{ value }}
        </text>
      </g>
      <g class="art-secondary" text-anchor="middle" font-size="17">
        <text x="300" y="155">分治</text>
        <text x="300" y="256">合并</text>
      </g>
    </g>
    <g v-else-if="visual === 'graph'">
      <g class="art-lines" fill="none" stroke-width="5">
        <path
          d="m66 206 144-119 180 61 145 105-177 77-165-65L66 206M210 87l-17 178 197-117-32 182"
        />
      </g>
      <path
        class="art-accent-stroke"
        d="m66 206 144-119 180 61 145 105"
        fill="none"
        stroke-width="9"
        stroke-linecap="round"
      />
      <g class="art-paper">
        <circle cx="193" cy="265" r="29" />
        <circle cx="358" cy="330" r="29" />
      </g>
      <g class="art-accent">
        <circle cx="66" cy="206" r="30" />
        <circle cx="210" cy="87" r="30" />
        <circle cx="390" cy="148" r="30" />
        <circle cx="535" cy="253" r="30" />
      </g>
      <g
        class="art-white"
        font-size="26"
        text-anchor="middle"
        dominant-baseline="central"
      >
        <text x="66" y="206">A</text>
        <text x="210" y="87">B</text>
        <text x="390" y="148">D</text>
        <text x="535" y="253">F</text>
      </g>
      <g
        class="art-ink"
        font-size="24"
        text-anchor="middle"
        dominant-baseline="central"
      >
        <text x="193" y="265">C</text>
        <text x="358" y="330">E</text>
      </g>
    </g>
    <g v-else-if="visual === 'dp'" font-size="29" text-anchor="middle">
      <g
        v-for="(row, y) in [
          [0, 0, 0, 0, 0],
          [0, 2, 2, 2, 2],
          [0, 2, 3, 5, 5],
          [0, 2, 3, 5, 6]
        ]"
        :key="y"
      >
        <g v-for="(value, x) in row" :key="x">
          <rect
            :class="y === 3 && x === 4 ? 'art-accent' : 'art-paper'"
            :x="62 + x * 98"
            :y="38 + y * 82"
            width="86"
            height="70"
            rx="13"
          />
          <text
            :class="y === 3 && x === 4 ? 'art-white' : 'art-ink'"
            :x="105 + x * 98"
            :y="84 + y * 82"
          >
            {{ value }}
          </text>
        </g>
      </g>
    </g>
    <g v-else-if="visual === 'tree'">
      <g class="art-lines" stroke-width="5" fill="none">
        <path
          d="m300 82-127 107-81 124M173 189l75 124M300 82l127 107-75 124M427 189l81 124"
        />
      </g>
      <g class="art-paper">
        <circle cx="92" cy="313" r="33" />
        <circle cx="248" cy="313" r="33" />
        <circle cx="352" cy="313" r="33" />
        <circle cx="508" cy="313" r="33" />
      </g>
      <g class="art-accent">
        <circle cx="173" cy="189" r="38" />
        <circle cx="427" cy="189" r="38" />
      </g>
      <circle class="art-dark" cx="300" cy="82" r="42" />
      <g
        class="art-white"
        font-size="28"
        text-anchor="middle"
        dominant-baseline="central"
      >
        <text x="300" y="82">n</text>
        <text x="173" y="189">L</text>
        <text x="427" y="189">R</text>
      </g>
    </g>
    <g v-else-if="visual === 'sum'">
      <path
        class="art-lines"
        fill="none"
        stroke-width="5"
        stroke-linecap="round"
        d="M156 160v34q0 24 24 24h96m168-58v34q0 24-24 24h-96M300 240v48"
      />
      <rect
        class="art-paper"
        x="64"
        y="60"
        width="184"
        height="108"
        rx="26"
        transform="rotate(-5 156 114)"
      />
      <rect
        class="art-accent"
        x="352"
        y="60"
        width="184"
        height="108"
        rx="26"
        transform="rotate(5 444 114)"
      />
      <circle class="art-paper" cx="300" cy="218" r="35" />
      <rect class="art-dark" x="174" y="286" width="252" height="82" rx="24" />
      <g font-size="58" text-anchor="middle">
        <text class="art-ink" x="156" y="135">a</text>
        <text class="art-white" x="444" y="135">b</text>
        <text class="art-ink" x="300" y="237">+</text>
        <text class="art-white" x="300" y="344" font-size="43">a + b</text>
      </g>
    </g>
    <g v-else-if="visual === 'lesson'">
      <rect
        class="art-paper"
        x="118"
        y="55"
        width="380"
        height="270"
        rx="26"
        transform="rotate(6 308 190)"
      />
      <rect
        class="art-dark"
        x="64"
        y="86"
        width="380"
        height="244"
        rx="26"
        transform="rotate(-4 254 208)"
      />
      <g
        class="art-accent-stroke"
        fill="none"
        stroke-width="11"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="m178 157-42 40 42 40m107-80 42 40-42 40m-37-92-22 104" />
      </g>
      <g class="art-paper">
        <circle cx="104" cy="119" r="5" />
        <circle cx="124" cy="118" r="5" />
        <circle cx="144" cy="116" r="5" />
      </g>
      <circle class="art-accent" cx="454" cy="282" r="76" />
      <path class="art-white" d="m438 248 46 34-46 34z" />
      <g class="art-lines" fill="none" stroke-width="4">
        <path d="M487 74v30m-54-30v30m-54-30v30" />
      </g>
    </g>
    <g v-else>
      <rect class="art-dark" x="75" y="65" width="450" height="270" rx="30" />
      <g
        class="art-accent-stroke"
        stroke-width="13"
        fill="none"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="m230 148-54 52 54 52m140-104 54 52-54 52m-53-131-34 158" />
      </g>
      <g class="art-paper">
        <circle cx="108" cy="95" r="5" />
        <circle cx="129" cy="95" r="5" />
        <circle cx="150" cy="95" r="5" />
      </g>
    </g>
  </svg>
</template>
<style scoped>
.assignment-artwork {
  display: block;
  width: 100%;
  height: 100%;
  font-family: var(--font-ui, 'Segoe UI', 'Microsoft YaHei', sans-serif);
}
.art-lines {
  stroke: var(--art-line, #9bacc9);
}
.art-accent-stroke {
  stroke: var(--primary, #285ed9);
}
.art-accent {
  fill: var(--primary, #285ed9);
}
.art-paper {
  fill: var(--surface, #fff);
}
.art-dark {
  fill: var(--ink, #14243e);
}
.art-ink {
  fill: var(--ink, #14243e);
}
.art-white {
  fill: #fff;
}
.art-secondary {
  fill: var(--muted, #53647d);
}
</style>
