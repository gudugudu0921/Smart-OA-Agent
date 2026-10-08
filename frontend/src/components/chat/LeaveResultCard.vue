<script setup>
import { leaveTypeLabels, statusLabels, statusTagType } from '../../utils/format'
defineProps({ item: { type: Object, required: true } })
</script>

<template>
  <div class="leave-card">
    <div class="card-head"><strong>{{ leaveTypeLabels[item.leave_type] || item.leave_type }}</strong><el-tag :type="statusTagType(item.status)" size="small">{{ statusLabels[item.status] || item.status }}</el-tag></div>
    <div class="card-id">{{ item.application_id || item.id }}</div>
    <div class="card-grid">
      <span>日期</span><b>{{ item.start_date }} 至 {{ item.end_date }}</b>
      <span>天数</span><b>{{ item.leave_days }} 天</b>
      <span>主管</span><el-tag :type="statusTagType(item.manager_status)" size="small">{{ statusLabels[item.manager_status] || item.manager_status }}</el-tag>
      <span>HR</span><el-tag :type="statusTagType(item.hr_status)" size="small">{{ statusLabels[item.hr_status] || item.hr_status }}</el-tag>
    </div>
  </div>
</template>

<style scoped>
.leave-card { width: 100%; max-width: 520px; margin-top: 10px; padding: 13px; border: 1px solid #dfe7f1; border-radius: 8px; background: #fff; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.card-id { margin: 6px 0 10px; color: #7b8798; font: 11px ui-monospace, monospace; }
.card-grid { display: grid; grid-template-columns: 54px 1fr; gap: 7px 10px; align-items: center; font-size: 12px; }
.card-grid span { color: #8793a4; }
</style>
