const state = {
  snapshot: null,
  activeView: location.hash.replace('#', '') || 'overview',
  selectedOrderId: null,
  autoRefresh: true,
  filters: {
    query: '',
    building: 'all',
    status: 'all',
    deviceSearch: '',
    riskFilter: 'all',
    deviceSort: 'risk',
  },
};

const $ = (id) => document.getElementById(id);
const VIEW_IDS = ['overview', 'workflow', 'alerts', 'devices', 'settings'];

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

function fmtText(value) {
  return escapeHtml(value ?? '-');
}

function postJson(url, payload) {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then((res) => res.json());
}

function switchView(view) {
  if (!VIEW_IDS.includes(view)) view = 'overview';
  state.activeView = view;
  location.hash = `#${view}`;
  document.querySelectorAll('.tab').forEach((tab) => {
    tab.classList.toggle('active', tab.dataset.view === view);
  });
  document.querySelectorAll('.view').forEach((section) => {
    section.classList.toggle('active', section.dataset.view === view);
  });
}

function currentOrders(snapshot) {
  const q = state.filters.query.trim().toLowerCase();
  return (snapshot.work_orders || []).filter((order) => {
    const matchesQuery = !q || [
      order.order_id,
      order.unit_id,
      order.building_id,
      order.title,
      order.kind,
      order.assignee,
    ].some((value) => String(value ?? '').toLowerCase().includes(q));
    const matchesBuilding = state.filters.building === 'all' || order.building_id === state.filters.building;
    const matchesStatus = state.filters.status === 'all' || order.status === state.filters.status;
    return matchesQuery && matchesBuilding && matchesStatus;
  });
}

function currentUnits(snapshot) {
  const q = state.filters.deviceSearch.trim().toLowerCase();
  return (snapshot.units || []).filter((unit) => {
    const matchesQuery = !q || [unit.unit_id, unit.building_id, unit.household_type].some((value) => String(value ?? '').toLowerCase().includes(q));
    const risk = unit.risk_score >= 60 ? 'high' : unit.risk_score >= 35 ? 'medium' : 'low';
    const matchesRisk = state.filters.riskFilter === 'all' || state.filters.riskFilter === risk;
    return matchesQuery && matchesRisk;
  }).sort((a, b) => {
    if (state.filters.deviceSort === 'energy') return b.energy_today_kwh - a.energy_today_kwh;
    if (state.filters.deviceSort === 'alphabet') return a.unit_id.localeCompare(b.unit_id);
    return b.risk_score - a.risk_score;
  });
}

function buildKpiCards(snapshot) {
  const k = snapshot.kpis;
  return [
    ['住户数', k.household_count, `设备在线 ${k.active_device_count}`],
    ['安全评分', k.safety_score, `最近一小时告警 ${k.alerts_last_hour}`],
    ['开放工单', k.open_order_count, `逾期 ${k.overdue_order_count}`],
    ['今日能耗', k.total_energy_today_kwh, `平均温度 ${k.avg_temperature_c} ℃`],
    ['平均风险', k.avg_risk_score, `平均湿度 ${k.avg_humidity_pct} %`],
    ['当前通知', snapshot.notifications.length, `告警 ${snapshot.alerts.length}`],
  ];
}

function renderKpis(snapshot) {
  $('kpiGrid').innerHTML = buildKpiCards(snapshot).map(([label, value, delta]) => `
    <article class="kpi-card">
      <div class="label">${fmtText(label)}</div>
      <strong class="value">${escapeHtml(formatNumber(value))}</strong>
      <div class="delta">${fmtText(delta)}</div>
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
  const step = (w - pad * 2) / Math.max(1, trend.length - 1);
  const risks = trend.map((item) => Number(item.avg_risk_score ?? 0));
  const power = trend.map((item) => Number(item.total_power_kw ?? 0));
  const maxRisk = Math.max(...risks, 1);
  const maxPower = Math.max(...power, 1);

  const riskPoints = trend.map((item, idx) => {
    const x = pad + idx * step;
    const y = h - pad - (item.avg_risk_score / maxRisk) * 160;
    return `${x},${y}`;
  }).join(' ');
  const powerPoints = trend.map((item, idx) => {
    const x = pad + idx * step;
    const y = h - pad - (item.total_power_kw / maxPower) * 120;
    return `${x},${y}`;
  }).join(' ');

  svg.innerHTML = `
    <defs>
      <linearGradient id="riskGrad" x1="0%" x2="100%">
        <stop offset="0%" stop-color="#0f766e" />
        <stop offset="100%" stop-color="#b91c1c" />
      </linearGradient>
      <linearGradient id="powerGrad" x1="0%" x2="100%">
        <stop offset="0%" stop-color="#2563eb" />
        <stop offset="100%" stop-color="#f59e0b" />
      </linearGradient>
    </defs>
    <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" stroke="#d8cab7" />
    <polyline points="${riskPoints}" fill="none" stroke="url(#riskGrad)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></polyline>
    <polyline points="${powerPoints}" fill="none" stroke="url(#powerGrad)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="10 6"></polyline>
    ${trend.map((item, idx) => {
      const x = pad + idx * step;
      const y1 = h - pad - (item.avg_risk_score / maxRisk) * 160;
      const y2 = h - pad - (item.total_power_kw / maxPower) * 120;
      return `
        <circle cx="${x}" cy="${y1}" r="3.6" fill="#0f766e"></circle>
        <circle cx="${x}" cy="${y2}" r="3.6" fill="#2563eb"></circle>
        <text x="${x}" y="${h - 8}" text-anchor="middle" font-size="11" fill="#64748b">${escapeHtml(item.time)}</text>
      `;
    }).join('')}
  `;

  $('workflowSummary').textContent = `工单 ${snapshot.workflow_counts.new + snapshot.workflow_counts.assigned + snapshot.workflow_counts.processing + snapshot.workflow_counts.resolved} | 逾期 ${snapshot.kpis.overdue_order_count}`;
}

function renderBuildingCards(snapshot) {
  const cards = snapshot.building_cards || [];
  $('buildingCards').innerHTML = cards.map((item) => `
    <article class="building-card" data-building-focus="${escapeHtml(item.building_id)}">
      <div class="title">${escapeHtml(item.building_id)} 楼</div>
      <div class="meta">住户 ${item.household_count} · 开放工单 ${item.open_orders}</div>
      <div class="meta">平均风险 ${formatNumber(item.avg_risk_score)} · 今日能耗 ${formatNumber(item.energy_today_kwh)} kWh</div>
      <div class="meta">紧急工单 ${item.critical_orders}</div>
    </article>
  `).join('');
}

function orderActions(order) {
  switch (order.status) {
    case 'new':
      return [{ action: 'assign', label: '派单', cls: 'primary' }];
    case 'assigned':
      return [
        { action: 'start', label: '开始处理', cls: 'primary' },
        { action: 'resolve', label: '直接完成', cls: 'warn' },
      ];
    case 'processing':
      return [
        { action: 'resolve', label: '标记已处理', cls: 'primary' },
        { action: 'escalate', label: '升级', cls: 'warn' },
      ];
    case 'resolved':
      return [{ action: 'close', label: '关闭工单', cls: 'primary' }];
    case 'closed':
      return [{ action: 'reopen', label: '重新打开', cls: '' }];
    default:
      return [];
  }
}

function renderOrderDetail(snapshot, order) {
  const panel = $('orderDetail');
  if (!order) {
    panel.innerHTML = `
      <div class="panel-head">
        <h2>工单详情</h2>
        <span class="panel-note">请选择左侧工单</span>
      </div>
      <p class="detail-note">这里会展示工单的全部信息、处理记录和可执行动作。</p>
    `;
    return;
  }

  const history = order.history || [];
  panel.innerHTML = `
    <div class="panel-head">
      <h2>工单详情</h2>
      <span class="panel-note">${escapeHtml(order.order_id)}</span>
    </div>
    <h3 class="detail-title">${escapeHtml(order.title)}</h3>
    <div class="detail-meta">${escapeHtml(order.unit_id)} · ${escapeHtml(order.building_id)} · ${escapeHtml(order.kind)}</div>
    <div class="detail-badges">
      <span class="badge-soft">${escapeHtml(order.status)}</span>
      <span class="badge-soft">${escapeHtml(order.priority)}</span>
      <span class="badge-soft">${escapeHtml(order.severity)} 级</span>
      <span class="badge-soft">${escapeHtml(order.assignee)}</span>
    </div>
    <div class="detail-note">${escapeHtml(order.description)}</div>
    <div class="progress"><span style="width:${Math.max(5, Math.min(100, order.progress_pct))}%"></span></div>
    <div class="detail-note">进度 ${escapeHtml(order.progress_pct)}% · 发生 ${escapeHtml(order.occurrences)} 次 · 更新时间 ${escapeHtml(order.updated_at)}</div>
    <div class="detail-actions">
      ${orderActions(order).map((item) => `
        <button class="action-btn ${item.cls}" data-order-action="${item.action}" data-order-id="${order.order_id}">
          ${escapeHtml(item.label)}
        </button>
      `).join('')}
    </div>
    <div class="detail-note">建议：${escapeHtml(order.description)}</div>
    <div class="history-list">
      ${history.map((item) => `
        <div class="history-item">
          <strong>${escapeHtml(item.actor)}</strong> · ${escapeHtml(item.action)}<br />
          ${escapeHtml(item.time)}<br />
          ${escapeHtml(item.note)}
        </div>
      `).join('')}
    </div>
  `;
  panel.querySelectorAll('[data-order-action]').forEach((btn) => {
    btn.addEventListener('click', () => sendOrderAction(btn.dataset.orderId, btn.dataset.orderAction));
  });
}

function renderWorkflow(snapshot) {
  const filtered = currentOrders(snapshot);
  const byStatus = {
    new: filtered.filter((item) => item.status === 'new'),
    assigned: filtered.filter((item) => item.status === 'assigned'),
    processing: filtered.filter((item) => item.status === 'processing'),
    resolved: filtered.filter((item) => item.status === 'resolved'),
  };

  $('buildingFilter').innerHTML = ['all', ...new Set((snapshot.work_orders || []).map((item) => item.building_id))].map((item) => `
    <option value="${escapeHtml(item)}">${item === 'all' ? '全部楼栋' : escapeHtml(item)}</option>
  `).join('');
  $('statusFilter').innerHTML = ['all', 'new', 'assigned', 'processing', 'resolved', 'closed'].map((item) => `
    <option value="${escapeHtml(item)}">${item === 'all' ? '全部状态' : escapeHtml(item)}</option>
  `).join('');
  $('orderSearch').value = state.filters.query;
  $('buildingFilter').value = state.filters.building;
  $('statusFilter').value = state.filters.status;
  $('autoRefreshSelect').value = state.autoRefresh ? 'on' : 'off';

  const laneDefs = [
    ['new', '待派单'],
    ['assigned', '已派单'],
    ['processing', '处理中'],
    ['resolved', '待闭环'],
  ];

  $('workflowBoard').innerHTML = laneDefs.map(([key, label]) => `
    <section class="lane">
      <div class="lane-head">
        <div class="lane-title">${escapeHtml(label)}</div>
        <div class="lane-count">${byStatus[key].length} 条</div>
      </div>
      <div class="lane-body">
        ${byStatus[key].map((order) => `
          <article class="order-card ${order.order_id === state.selectedOrderId ? 'selected' : ''}" data-order-id="${order.order_id}">
            <div class="order-top">
              <div class="order-title">${escapeHtml(order.unit_id)} · ${escapeHtml(order.title)}</div>
              <span class="priority-tag">${escapeHtml(order.priority)} / ${escapeHtml(order.severity)}级</span>
            </div>
            <div class="order-meta">${escapeHtml(order.building_id)} | ${escapeHtml(order.kind)} | ${escapeHtml(order.created_at)}</div>
            <div class="order-desc">${escapeHtml(order.description)}</div>
            <div class="order-footer">
              <span>${escapeHtml(order.status)} · 进度 ${escapeHtml(order.progress_pct)}%</span>
              <span class="detail-note">点击查看</span>
            </div>
          </article>
        `).join('')}
      </div>
    </section>
  `).join('');

  const selected =
    filtered.find((item) => item.order_id === state.selectedOrderId) ||
    filtered[0] ||
    snapshot.work_orders?.find((item) => item.order_id === state.selectedOrderId) ||
    snapshot.work_orders?.[0] ||
    null;
  if (selected) state.selectedOrderId = selected.order_id;
  renderOrderDetail(snapshot, selected);

  $('workflowBoard').querySelectorAll('[data-order-id]').forEach((card) => {
    card.addEventListener('click', () => {
      state.selectedOrderId = card.dataset.orderId;
      renderWorkflow(snapshot);
    });
  });
}

function renderAlerts(snapshot) {
  const alertStats = [
    ['燃气泄漏', 'gas_leak'],
    ['烟雾超标', 'smoke_high'],
    ['用电过载', 'power_overload'],
    ['漏水告警', 'water_leak'],
    ['老人关怀', 'elderly_care'],
    ['夜间门磁', 'night_security'],
    ['空气质量', 'air_quality'],
  ];
  const alerts = snapshot.alerts || [];
  $('alertStats').innerHTML = alertStats.map(([label, key]) => {
    const count = alerts.filter((item) => item.kind === key).length;
    const max = Math.max(...alerts.map((item) => item.severity), 1);
    const width = alerts.length ? Math.max(8, Math.round((count / Math.max(alerts.length, 1)) * 100)) : 8;
    return `
      <div class="alert-stat">
        <span>${escapeHtml(label)}</span>
        <strong>${count}</strong>
        <div class="bar" style="grid-column: 1 / -1"><span style="width:${width}%"></span></div>
      </div>
    `;
  }).join('');

  $('alertFeed').innerHTML = alerts.map((item) => `
    <article class="feed-item ${item.severity >= 4 ? 'critical' : 'warning'}" data-order-link="${escapeHtml(item.order_id || '')}">
      <div class="title">${escapeHtml(item.title)} · ${escapeHtml(item.unit_id)}</div>
      <div class="meta">${escapeHtml(item.summary)}</div>
      <div class="meta">建议：${escapeHtml(item.recommendation)} | 工单：${escapeHtml(item.order_id || '-')}</div>
    </article>
  `).join('') || '<div class="detail-note">暂无告警。</div>';

  $('alertNotificationFeed').innerHTML = (snapshot.notifications || []).map((item) => `
    <article class="feed-item ${item.level === 'critical' ? 'critical' : item.level === 'warning' ? 'warning' : ''}">
      <div class="title">${escapeHtml(item.title)}</div>
      <div class="meta">${escapeHtml(item.message)}</div>
      <div class="meta">${escapeHtml(item.created_at)} · 来源 ${escapeHtml(item.source)}</div>
    </article>
  `).join('') || '<div class="detail-note">暂无通知。</div>';
}

function renderDevices(snapshot) {
  const units = currentUnits(snapshot);
  $('unitGrid').innerHTML = units.map((item) => {
    const riskClass = item.risk_score >= 60 ? 'risk-high' : item.risk_score >= 35 ? 'risk-medium' : 'risk-low';
    const width = Math.max(8, Math.min(100, item.risk_score));
    return `
      <article class="unit-card">
        <div class="unit-head">
          <div>
            <div class="title">${escapeHtml(item.unit_id)}</div>
            <div class="meta">${escapeHtml(item.building_id)} 楼 · ${escapeHtml(item.household_type)} · ${escapeHtml(item.floor)} 层</div>
          </div>
          <span class="risk-pill ${riskClass}">${escapeHtml(item.mode)} / ${formatNumber(item.risk_score)}</span>
        </div>
        <div class="meta">温度 ${formatNumber(item.temperature_c)} ℃ · 湿度 ${formatNumber(item.humidity_pct)} % · 功率 ${formatNumber(item.power_w)} W</div>
        <div class="meta">燃气 ${formatNumber(item.gas_ppm)} ppm · 烟雾 ${formatNumber(item.smoke_ppm)} ppm · PM2.5 ${formatNumber(item.pm25)}</div>
        <div class="meta">门磁 ${item.door_open ? '开启' : '关闭'} · 漏水 ${item.water_leak ? '是' : '否'} · 能耗 ${formatNumber(item.energy_today_kwh)} kWh</div>
        <div class="sensor-bar"><span style="width:${width}%"></span></div>
      </article>
    `;
  }).join('');
}

function renderSettings(snapshot) {
  $('settingSummary').innerHTML = `
    <div class="detail-note">模拟时间：${escapeHtml(snapshot.simulation.sim_time)}</div>
    <div class="detail-note">楼栋数：${escapeHtml(snapshot.building_cards.length)}</div>
    <div class="detail-note">工单总数：${escapeHtml(snapshot.work_orders.length)}</div>
    <div class="detail-note">告警总数：${escapeHtml(snapshot.alerts.length)}</div>
    <div class="detail-note">自动刷新：${state.autoRefresh ? '开启' : '关闭'}</div>
  `;
}

function renderPage(snapshot) {
  renderKpis(snapshot);
  renderTrend(snapshot);
  renderBuildingCards(snapshot);
  renderWorkflow(snapshot);
  renderAlerts(snapshot);
  renderDevices(snapshot);
  renderSettings(snapshot);

  $('simStatusText').textContent = snapshot.simulation.paused ? '已暂停' : '实时运行';
  $('simTime').textContent = `模拟时间：${snapshot.simulation.sim_time} | 第 ${snapshot.simulation.tick_index} 轮`;
}

async function sendOrderAction(orderId, action) {
  await postJson('/api/work-orders/action', {
    order_id: orderId,
    action,
    actor: '前端调度员',
    note: `前端执行 ${action}`,
  });
  await refreshSnapshot();
}

async function sendControl(action) {
  await postJson('/api/sim/control', { action });
  await refreshSnapshot();
}

function exportSnapshot() {
  const blob = new Blob([JSON.stringify(state.snapshot, null, 2)], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `snapshot-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

async function refreshSnapshot() {
  const response = await fetch('/api/snapshot', { cache: 'no-store' });
  state.snapshot = await response.json();
  renderPage(state.snapshot);
}

function bindEvents() {
  document.querySelectorAll('.tab').forEach((tab) => {
    tab.addEventListener('click', () => switchView(tab.dataset.view));
  });

  document.querySelectorAll('[data-go]').forEach((btn) => {
    btn.addEventListener('click', () => switchView(btn.dataset.go));
  });

  document.body.addEventListener('click', (event) => {
    const building = event.target.closest('[data-building-focus]');
    if (building) {
      state.filters.building = building.dataset.buildingFocus;
      switchView('workflow');
      refreshSnapshot();
      return;
    }

    const orderLink = event.target.closest('[data-order-link]');
    if (orderLink && orderLink.dataset.orderLink) {
      state.selectedOrderId = orderLink.dataset.orderLink;
      switchView('workflow');
      refreshSnapshot();
      return;
    }
  });

  document.body.addEventListener('click', (event) => {
    const control = event.target.closest('[data-control]');
    if (!control) return;
    sendControl(control.dataset.control);
  });

  document.body.addEventListener('click', (event) => {
    if (!event.target.matches('[data-action="export"]')) return;
    exportSnapshot();
  });

  $('orderSearch').addEventListener('input', (event) => {
    state.filters.query = event.target.value;
    renderWorkflow(state.snapshot);
  });
  $('buildingFilter').addEventListener('change', (event) => {
    state.filters.building = event.target.value;
    renderWorkflow(state.snapshot);
  });
  $('statusFilter').addEventListener('change', (event) => {
    state.filters.status = event.target.value;
    renderWorkflow(state.snapshot);
  });
  $('autoRefreshSelect').addEventListener('change', (event) => {
    state.autoRefresh = event.target.value === 'on';
  });

  $('deviceSearch').addEventListener('input', (event) => {
    state.filters.deviceSearch = event.target.value;
    renderDevices(state.snapshot);
  });
  $('riskFilter').addEventListener('change', (event) => {
    state.filters.riskFilter = event.target.value;
    renderDevices(state.snapshot);
  });
  $('deviceSort').addEventListener('change', (event) => {
    state.filters.deviceSort = event.target.value;
    renderDevices(state.snapshot);
  });

  window.addEventListener('hashchange', () => switchView(location.hash.replace('#', '') || 'overview'));
}

bindEvents();
switchView(state.activeView);
refreshSnapshot().catch((error) => {
  console.error(error);
  document.body.insertAdjacentHTML('beforeend', `<pre style="padding:24px;color:#b91c1c">加载失败：${escapeHtml(error.message)}</pre>`);
});

setInterval(() => {
  if (state.autoRefresh) refreshSnapshot().catch(() => {});
}, 2500);

