const state = { snapshot: null };

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function formatNumber(value, digits = 1) {
  return Number(value ?? 0).toFixed(digits);
}

function orderActions(status) {
  switch (status) {
    case 'new':
      return [{ action: 'assign', label: '派单', className: 'primary' }];
    case 'assigned':
      return [
        { action: 'start', label: '开始处理', className: 'primary' },
        { action: 'resolve', label: '直接完成', className: 'warn' },
      ];
    case 'processing':
      return [
        { action: 'resolve', label: '标记已处理', className: 'primary' },
        { action: 'close', label: '闭环', className: '' },
      ];
    case 'resolved':
      return [{ action: 'close', label: '关闭工单', className: 'primary' }];
    case 'closed':
      return [{ action: 'reopen', label: '重新打开', className: '' }];
    default:
      return [];
  }
}

function renderKpis(snapshot) {
  const k = snapshot.kpis;
  const cards = [
    ['住户数', k.household_count, `设备在线 ${k.active_device_count}`],
    ['安全评分', k.safety_score, `最近一小时告警 ${k.alerts_last_hour}`],
    ['开放工单', k.open_order_count, `逾期 ${k.overdue_order_count}`],
    ['今日能耗', k.total_energy_today_kwh, `平均温度 ${k.avg_temperature_c} ℃`],
    ['平均风险', k.avg_risk_score, `平均湿度 ${k.avg_humidity_pct} %`],
    ['当前告警', snapshot.alerts.length, `待处理通知 ${snapshot.notifications.length}`],
  ];

  $('kpiGrid').innerHTML = cards.map(([label, value, delta]) => `
    <article class="kpi-card">
      <div class="label">${escapeHtml(label)}</div>
      <strong class="value">${escapeHtml(formatNumber(value, 1))}</strong>
      <div class="delta">${escapeHtml(delta)}</div>
    </article>
  `).join('');
}

function renderTrend(snapshot) {
  const trend = snapshot.trend || [];
  const svg = $('trendChart');
  if (!trend.length) {
    svg.innerHTML = '';
    return;
  }

  const w = 900;
  const h = 260;
  const pad = 28;
  const xStep = (w - pad * 2) / Math.max(1, trend.length - 1);
  const risks = trend.map((item) => Number(item.avg_risk_score ?? 0));
  const energy = trend.map((item) => Number(item.total_power_kw ?? 0));
  const maxRisk = Math.max(...risks, 1);
  const maxEnergy = Math.max(...energy, 1);
  const riskPoints = trend.map((item, idx) => {
    const x = pad + idx * xStep;
    const y = h - pad - (item.avg_risk_score / maxRisk) * 160;
    return `${x},${y}`;
  }).join(' ');
  const energyPoints = trend.map((item, idx) => {
    const x = pad + idx * xStep;
    const y = h - pad - (item.total_power_kw / maxEnergy) * 120;
    return `${x},${y}`;
  }).join(' ');

  svg.innerHTML = `
    <defs>
      <linearGradient id="riskGrad" x1="0%" x2="100%">
        <stop offset="0%" stop-color="#0f766e" />
        <stop offset="100%" stop-color="#b91c1c" />
      </linearGradient>
      <linearGradient id="energyGrad" x1="0%" x2="100%">
        <stop offset="0%" stop-color="#2563eb" />
        <stop offset="100%" stop-color="#f59e0b" />
      </linearGradient>
    </defs>
    <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" stroke="#d8cab7" />
    <polyline points="${riskPoints}" fill="none" stroke="url(#riskGrad)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></polyline>
    <polyline points="${energyPoints}" fill="none" stroke="url(#energyGrad)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="10 6"></polyline>
    ${trend.map((item, idx) => {
      const x = pad + idx * xStep;
      const y1 = h - pad - (item.avg_risk_score / maxRisk) * 160;
      const y2 = h - pad - (item.total_power_kw / maxEnergy) * 120;
      return `
        <circle cx="${x}" cy="${y1}" r="3.6" fill="#0f766e"></circle>
        <circle cx="${x}" cy="${y2}" r="3.6" fill="#2563eb"></circle>
        <text x="${x}" y="${h - 8}" text-anchor="middle" font-size="11" fill="#64748b">${escapeHtml(item.time)}</text>
      `;
    }).join('')}
  `;
}

function renderBuildingCards(snapshot) {
  $('buildingCards').innerHTML = (snapshot.building_cards || []).map((item) => `
    <article class="building-card">
      <div class="title">${escapeHtml(item.building_id)} 楼</div>
      <div class="building-meta">住户 ${item.household_count} · 开放工单 ${item.open_orders}</div>
      <div class="building-meta">平均风险 ${formatNumber(item.avg_risk_score)} · 今日能耗 ${formatNumber(item.energy_today_kwh)} kWh</div>
      <div class="building-meta">紧急工单 ${item.critical_orders}</div>
    </article>
  `).join('');
}

function renderWorkflow(snapshot) {
  const lanes = [
    { status: 'new', title: '待派单' },
    { status: 'assigned', title: '已派单' },
    { status: 'processing', title: '处理中' },
    { status: 'resolved', title: '待闭环' },
  ];
  const orders = snapshot.work_orders || [];
  $('workflowCounts').textContent = `new ${snapshot.workflow_counts.new} / assigned ${snapshot.workflow_counts.assigned} / processing ${snapshot.workflow_counts.processing} / resolved ${snapshot.workflow_counts.resolved}`;
  $('workflowBoard').innerHTML = lanes.map((lane) => {
    const laneOrders = orders.filter((order) => order.status === lane.status);
    return `
      <section class="lane">
        <h3>${lane.title}</h3>
        <div class="count">${laneOrders.length} 条</div>
        <div class="card-list">
          ${laneOrders.map(renderOrderCard).join('')}
        </div>
      </section>
    `;
  }).join('');
  bindActionButtons();
}

function renderOrderCard(order) {
  const template = $('orderCardTemplate');
  const node = template.content.firstElementChild.cloneNode(true);
  node.dataset.orderId = order.order_id;
  node.querySelector('.order-title').textContent = `${order.unit_id} · ${order.title}`;
  node.querySelector('.order-meta').textContent = `${order.building_id} | ${order.kind} | ${order.created_at}`;
  node.querySelector('.priority-tag').textContent = `${order.priority} / ${order.severity}级`;
  node.querySelector('.order-desc').textContent = order.description;
  node.querySelector('.order-status').textContent = `状态：${order.status} | 进度 ${order.progress_pct}% | 责任组 ${order.assignee}`;
  const actionWrap = node.querySelector('.order-actions');
  actionWrap.innerHTML = orderActions(order.status).map((item) => `
    <button class="action-btn ${item.className || ''}" data-order="${order.order_id}" data-action="${item.action}">
      ${escapeHtml(item.label)}
    </button>
  `).join('');
  return node.outerHTML;
}

function bindActionButtons() {
  document.querySelectorAll('[data-order]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      await sendAction(btn.dataset.order, btn.dataset.action);
    });
  });
}

function renderAlerts(snapshot) {
  $('alertFeed').innerHTML = (snapshot.alerts || []).map((item) => `
    <article class="feed-item ${item.severity >= 4 ? 'critical' : 'warning'}">
      <div class="title">${escapeHtml(item.title)} · ${escapeHtml(item.unit_id)}</div>
      <div class="meta">${escapeHtml(item.summary)}</div>
      <div class="meta">建议：${escapeHtml(item.recommendation)} | 工单：${escapeHtml(item.order_id || '-')}</div>
    </article>
  `).join('') || '<div class="meta">暂无最新告警。</div>';
}

function renderNotifications(snapshot) {
  $('notificationFeed').innerHTML = (snapshot.notifications || []).map((item) => `
    <article class="feed-item ${item.level === 'critical' ? 'critical' : item.level === 'warning' ? 'warning' : ''}">
      <div class="title">${escapeHtml(item.title)}</div>
      <div class="meta">${escapeHtml(item.message)}</div>
      <div class="meta">${escapeHtml(item.created_at)} · 来源 ${escapeHtml(item.source)}</div>
    </article>
  `).join('') || '<div class="meta">暂无通知。</div>';
}

function renderUnits(snapshot) {
  $('unitGrid').innerHTML = (snapshot.units || []).map((item) => {
    const riskClass = item.risk_score >= 60 ? 'risk-high' : item.risk_score >= 35 ? 'risk-medium' : 'risk-low';
    const sensorWidth = Math.min(100, Math.max(8, item.risk_score));
    return `
      <article class="unit-card">
        <div class="unit-title">
          <strong>${escapeHtml(item.unit_id)}</strong>
          <span class="risk-pill ${riskClass}">${escapeHtml(item.mode)} / ${formatNumber(item.risk_score)}</span>
        </div>
        <div class="unit-meta">${escapeHtml(item.building_id)} 楼 · ${item.household_type} · ${item.floor} 层</div>
        <div class="unit-meta">温度 ${formatNumber(item.temperature_c)} ℃ · 湿度 ${formatNumber(item.humidity_pct)} % · 功率 ${formatNumber(item.power_w)} W</div>
        <div class="unit-meta">燃气 ${formatNumber(item.gas_ppm)} ppm · 烟雾 ${formatNumber(item.smoke_ppm)} ppm · PM2.5 ${formatNumber(item.pm25)}</div>
        <div class="unit-meta">门磁 ${item.door_open ? '开启' : '关闭'} · 漏水 ${item.water_leak ? '是' : '否'} · 能耗 ${formatNumber(item.energy_today_kwh)} kWh</div>
        <div class="sensor-bar"><span style="width:${sensorWidth}%"></span></div>
      </article>
    `;
  }).join('');
}

async function sendAction(orderId, action) {
  await fetch('/api/work-orders/action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      order_id: orderId,
      action,
      actor: '前端调度员',
      note: `前端执行 ${action}`,
    }),
  });
  await refreshSnapshot();
}

async function controlSimulation(action) {
  await fetch('/api/sim/control', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  });
  await refreshSnapshot();
}

async function refreshSnapshot() {
  const response = await fetch('/api/snapshot', { cache: 'no-store' });
  state.snapshot = await response.json();
  const snapshot = state.snapshot;
  $('simTime').textContent = `模拟时间：${snapshot.simulation.sim_time} | 第 ${snapshot.simulation.tick_index} 轮`;
  $('toggleBtn').textContent = snapshot.simulation.paused ? '继续运行' : '暂停';
  $('simStatus').innerHTML = snapshot.simulation.paused
    ? '<span class="dot" style="background:#f59e0b"></span><span>已暂停</span>'
    : '<span class="dot"></span><span>实时运行</span>';

  renderKpis(snapshot);
  renderTrend(snapshot);
  renderBuildingCards(snapshot);
  renderWorkflow(snapshot);
  renderAlerts(snapshot);
  renderNotifications(snapshot);
  renderUnits(snapshot);
}

$('refreshBtn').addEventListener('click', refreshSnapshot);
$('toggleBtn').addEventListener('click', async () => {
  await controlSimulation('toggle');
});
$('stepBtn').addEventListener('click', async () => {
  await controlSimulation('tick');
});

refreshSnapshot().catch((error) => {
  console.error(error);
  document.body.insertAdjacentHTML('beforeend', `<pre style="padding:24px;color:#b91c1c">加载失败：${escapeHtml(error.message)}</pre>`);
});

setInterval(() => {
  refreshSnapshot().catch(() => {});
}, 2500);

