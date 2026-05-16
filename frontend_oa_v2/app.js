const AUTH_TOKEN_KEY = 'community_auth_token';
const state = {
  snapshot: null,
  user: null,
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
const VIEW_IDS = ['overview', 'workflow', 'alerts', 'devices', 'innovation', 'settings'];

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function formatNumber(value, digits = 1) {
  return Number(value ?? 0).toFixed(digits);
}

function text(value) {
  return escapeHtml(value ?? '-');
}

function getToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY) || '';
}

function clearSession() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

function redirectToLogin() {
  const redirect = `${location.pathname}${location.hash || ''}`;
  location.href = `/login.html?redirect=${encodeURIComponent(redirect)}`;
}

async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const token = getToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(url, {
    cache: 'no-store',
    ...options,
    headers,
  });

  if (response.status === 401) {
    clearSession();
    redirectToLogin();
    throw new Error('未登录或登录已过期');
  }

  return response;
}

async function getJson(url) {
  const response = await apiFetch(url);
  return response.json();
}

async function postJson(url, payload) {
  const response = await apiFetch(url, {
    method: 'POST',
    body: JSON.stringify(payload ?? {}),
  });
  return response.json();
}

function renderSessionCard() {
  if (!$('sessionUser') || !$('sessionMeta')) return;
  if (!state.user) {
    $('sessionUser').textContent = '未登录';
    $('sessionMeta').textContent = '请先登录后使用系统';
    return;
  }
  const expiresAt = String(state.user.expires_at || '').replace('T', ' ');
  $('sessionUser').textContent = `${state.user.username} / 社区管理员`;
  $('sessionMeta').textContent = `${state.user.email} · 会话有效至 ${expiresAt}`;
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

function renderKpis(snapshot) {
  const k = snapshot.kpis;
  const cards = [
    ['住户数', k.household_count, `设备在线 ${k.active_device_count}`],
    ['安全评分', k.safety_score, `最近一小时告警 ${k.alerts_last_hour}`],
    ['开放工单', k.open_order_count, `逾期 ${k.overdue_order_count}`],
    ['今日能耗', k.total_energy_today_kwh, `平均温度 ${k.avg_temperature_c} ℃`],
    ['平均风险', k.avg_risk_score, `平均湿度 ${k.avg_humidity_pct} %`],
    ['当前通知', snapshot.notifications.length, `告警 ${snapshot.alerts.length}`],
  ];
  $('kpiGrid').innerHTML = cards.map(([label, value, delta]) => `
    <article class="kpi-card">
      <div class="label">${text(label)}</div>
      <strong class="value">${escapeHtml(formatNumber(value))}</strong>
      <div class="delta">${text(delta)}</div>
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
  const h = 280;
  const padX = 36;
  const padTop = 28;
  const padBottom = 52;
  const innerH = h - padTop - padBottom;
  const step = (w - padX * 2) / Math.max(1, trend.length - 1);
  const risks = trend.map((item) => Number(item.avg_risk_score ?? 0));
  const power = trend.map((item) => Number(item.total_power_kw ?? 0));
  const maxRisk = Math.max(...risks, 1);
  const maxPower = Math.max(...power, 1);
  const tickEvery = Math.max(1, Math.ceil(trend.length / 10));

  const riskPoints = trend.map((item, idx) => {
    const x = padX + idx * step;
    const y = h - padBottom - (item.avg_risk_score / maxRisk) * innerH;
    return `${x},${y}`;
  }).join(' ');

  const powerPoints = trend.map((item, idx) => {
    const x = padX + idx * step;
    const y = h - padBottom - (item.total_power_kw / maxPower) * innerH * 0.78;
    return `${x},${y}`;
  }).join(' ');

  const labels = trend.map((item, idx) => {
    if (idx % tickEvery !== 0 && idx !== trend.length - 1) return '';
    const x = padX + idx * step;
    return `<text x="${x}" y="${h - 18}" text-anchor="middle" font-size="11" fill="#64748b">${escapeHtml(item.time)}</text>`;
  }).join('');

  const grid = [0.25, 0.5, 0.75, 1].map((ratio) => {
    const y = h - padBottom - innerH * ratio;
    return `<line x1="${padX}" y1="${y}" x2="${w - padX}" y2="${y}" stroke="#e8ddcf" stroke-dasharray="4 6"></line>`;
  }).join('');

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
    ${grid}
    <line x1="${padX}" y1="${h - padBottom}" x2="${w - padX}" y2="${h - padBottom}" stroke="#d8cab7" />
    <polyline points="${riskPoints}" fill="none" stroke="url(#riskGrad)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></polyline>
    <polyline points="${powerPoints}" fill="none" stroke="url(#powerGrad)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="10 6"></polyline>
    ${trend.map((item, idx) => {
      const x = padX + idx * step;
      const y1 = h - padBottom - (item.avg_risk_score / maxRisk) * innerH;
      const y2 = h - padBottom - (item.total_power_kw / maxPower) * innerH * 0.78;
      return `
        <circle cx="${x}" cy="${y1}" r="3.4" fill="#0f766e"></circle>
        <circle cx="${x}" cy="${y2}" r="3.4" fill="#2563eb"></circle>
      `;
    }).join('')}
    ${labels}
    <text x="${padX}" y="18" font-size="12" fill="#0f766e">风险分</text>
    <text x="${w - padX - 48}" y="18" font-size="12" fill="#2563eb">功率(kW)</text>
  `;

  $('workflowSummary').textContent = `工单 ${snapshot.workflow_counts.new + snapshot.workflow_counts.assigned + snapshot.workflow_counts.processing + snapshot.workflow_counts.resolved} | 逾期 ${snapshot.kpis.overdue_order_count}`;
}

function renderAlertTypeChart(snapshot) {
  const svg = $('alertTypeChart');
  const alerts = snapshot.alerts || [];
  const types = [
    ['燃气泄漏', 'gas_leak'],
    ['烟雾超标', 'smoke_high'],
    ['用电过载', 'power_overload'],
    ['漏水告警', 'water_leak'],
    ['老人关怀', 'elderly_care'],
    ['空气质量', 'air_quality'],
  ];
  const counts = types.map(([label, key]) => ({
    label,
    count: alerts.filter((item) => item.kind === key).length,
  }));
  const max = Math.max(...counts.map((item) => item.count), 1);
  const w = 900;
  const left = 120;
  const usable = 900 - left - 60;
  const rowH = 28;
  svg.innerHTML = counts.map((item, idx) => {
    const y = 24 + idx * rowH;
    const width = (item.count / max) * usable;
    return `
      <text x="18" y="${y + 11}" font-size="12" fill="#556570">${escapeHtml(item.label)}</text>
      <rect x="${left}" y="${y}" width="${usable}" height="14" rx="7" fill="#eadfce"></rect>
      <rect x="${left}" y="${y}" width="${Math.max(8, width)}" height="14" rx="7" fill="url(#barGrad-${idx})"></rect>
      <text x="${left + Math.max(16, width) + 10}" y="${y + 11}" font-size="12" fill="#556570">${item.count}</text>
      <defs>
        <linearGradient id="barGrad-${idx}" x1="0%" x2="100%">
          <stop offset="0%" stop-color="#0f766e" />
          <stop offset="100%" stop-color="#f59e0b" />
        </linearGradient>
      </defs>
    `;
  }).join('');
}

function renderBuildingCards(snapshot) {
  $('buildingCards').innerHTML = (snapshot.building_cards || []).map((item) => `
    <article class="building-card" data-building-focus="${escapeHtml(item.building_id)}">
      <div class="title">${escapeHtml(item.building_id)} 楼</div>
      <div class="meta">住户 ${item.household_count} · 开放工单 ${item.open_orders}</div>
      <div class="meta">平均风险 ${formatNumber(item.avg_risk_score)} · 今日能耗 ${formatNumber(item.energy_today_kwh)} kWh</div>
      <div class="meta">紧急工单 ${item.critical_orders}</div>
    </article>
  `).join('');
}

function renderNotifications(targetId, items) {
  $(targetId).innerHTML = (items || []).map((item) => `
    <article class="feed-item ${item.level === 'critical' ? 'critical' : item.level === 'warning' ? 'warning' : ''}">
      <div class="title">${escapeHtml(item.title)}</div>
      <div class="meta">${escapeHtml(item.message)}</div>
      <div class="meta">${escapeHtml(item.created_at)} · 来源 ${escapeHtml(item.source)}</div>
    </article>
  `).join('') || '<div class="meta">暂无数据。</div>';
}

function filteredOrders(snapshot) {
  const query = state.filters.query.trim().toLowerCase();
  return (snapshot.work_orders || []).filter((order) => {
    const matchesQuery = !query || [
      order.order_id,
      order.unit_id,
      order.building_id,
      order.title,
      order.kind,
      order.assignee,
    ].some((value) => String(value ?? '').toLowerCase().includes(query));
    const matchesBuilding = state.filters.building === 'all' || order.building_id === state.filters.building;
    const matchesStatus = state.filters.status === 'all' || order.status === state.filters.status;
    return matchesQuery && matchesBuilding && matchesStatus;
  });
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

function renderOrderDetail(order) {
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
        <button class="action-btn ${item.cls}" data-order-id="${order.order_id}" data-order-action="${item.action}">
          ${escapeHtml(item.label)}
        </button>
      `).join('')}
    </div>
    <div class="detail-note">建议：${escapeHtml(order.description)}</div>
    <div class="history-list">
      ${(order.history || []).map((item) => `
        <div class="history-item">
          <strong>${escapeHtml(item.actor)}</strong> · ${escapeHtml(item.action)}<br />
          ${escapeHtml(item.time)}<br />
          ${escapeHtml(item.note)}
        </div>
      `).join('')}
    </div>
  `;

  panel.querySelectorAll('[data-order-action]').forEach((btn) => {
    btn.addEventListener('click', () => {
      sendOrderAction(btn.dataset.orderId, btn.dataset.orderAction).catch((error) => {
        window.alert(error.message);
      });
    });
  });
}

function renderWorkflow(snapshot) {
  const orders = filteredOrders(snapshot);
  const statuses = {
    new: orders.filter((item) => item.status === 'new'),
    assigned: orders.filter((item) => item.status === 'assigned'),
    processing: orders.filter((item) => item.status === 'processing'),
    resolved: orders.filter((item) => item.status === 'resolved'),
  };

  const buildings = ['all', ...new Set((snapshot.work_orders || []).map((item) => item.building_id))];
  $('buildingFilter').innerHTML = buildings.map((item) => `<option value="${escapeHtml(item)}">${item === 'all' ? '全部楼栋' : escapeHtml(item)}</option>`).join('');
  $('statusFilter').innerHTML = ['all', 'new', 'assigned', 'processing', 'resolved', 'closed'].map((item) => `<option value="${escapeHtml(item)}">${item === 'all' ? '全部状态' : escapeHtml(item)}</option>`).join('');
  $('buildingFilter').value = state.filters.building;
  $('statusFilter').value = state.filters.status;
  $('orderSearch').value = state.filters.query;
  $('autoRefreshSelect').value = state.autoRefresh ? 'on' : 'off';

  const lanes = [
    ['new', '待派单'],
    ['assigned', '已派单'],
    ['processing', '处理中'],
    ['resolved', '待闭环'],
  ];

  $('workflowBoard').innerHTML = lanes.map(([key, label]) => `
    <section class="lane">
      <div class="lane-head">
        <div class="lane-title">${escapeHtml(label)}</div>
        <div class="lane-count">${statuses[key].length} 条</div>
      </div>
      <div class="lane-body">
        ${statuses[key].map((order) => `
          <article class="order-card ${order.order_id === state.selectedOrderId ? 'selected' : ''}" data-order-card="${order.order_id}">
            <div class="order-top">
              <div class="order-title">${escapeHtml(order.unit_id)} · ${escapeHtml(order.title)}</div>
              <span class="priority-tag">${escapeHtml(order.priority)} / ${escapeHtml(order.severity)}级</span>
            </div>
            <div class="order-meta">${escapeHtml(order.building_id)} | ${escapeHtml(order.kind)} | ${escapeHtml(order.created_at)}</div>
            <div class="order-desc">${escapeHtml(order.description)}</div>
            <div class="order-footer">
              <span>${escapeHtml(order.status)} · 进度 ${escapeHtml(order.progress_pct)}%</span>
              <span class="meta">点击查看</span>
            </div>
          </article>
        `).join('') || '<div class="meta">暂无工单</div>'}
      </div>
    </section>
  `).join('');

  const selected = orders.find((item) => item.order_id === state.selectedOrderId) || orders[0] || null;
  if (selected) state.selectedOrderId = selected.order_id;
  renderOrderDetail(selected);

  $('workflowBoard').querySelectorAll('[data-order-card]').forEach((card) => {
    card.addEventListener('click', () => {
      state.selectedOrderId = card.dataset.orderCard;
      renderWorkflow(snapshot);
    });
  });
}

function renderAlertStats(snapshot) {
  const alertKinds = [
    ['燃气泄漏', 'gas_leak'],
    ['烟雾超标', 'smoke_high'],
    ['用电过载', 'power_overload'],
    ['漏水告警', 'water_leak'],
    ['老人关怀', 'elderly_care'],
    ['夜间门磁', 'night_security'],
    ['空气质量', 'air_quality'],
  ];
  const alerts = snapshot.alerts || [];
  $('alertStats').innerHTML = alertKinds.map(([label, key]) => {
    const count = alerts.filter((item) => item.kind === key).length;
    const width = alerts.length ? Math.max(8, Math.round((count / Math.max(alerts.length, 1)) * 100)) : 8;
    return `
      <div class="alert-stat">
        <span>${escapeHtml(label)}</span>
        <strong>${count}</strong>
        <div class="bar" style="grid-column: 1 / -1"><span style="width:${width}%"></span></div>
      </div>
    `;
  }).join('');
}

function renderAlerts(snapshot) {
  renderAlertStats(snapshot);
  renderNotifications('alertNotificationFeed', snapshot.notifications || []);
  $('alertFeed').innerHTML = (snapshot.alerts || []).map((item) => `
    <article class="feed-item ${item.severity >= 4 ? 'critical' : 'warning'}" data-alert-order="${escapeHtml(item.order_id || '')}">
      <div class="title">${escapeHtml(item.title)} · ${escapeHtml(item.unit_id)}</div>
      <div class="meta">${escapeHtml(item.summary)}</div>
      <div class="meta">建议：${escapeHtml(item.recommendation)} | 工单：${escapeHtml(item.order_id || '-')}</div>
    </article>
  `).join('') || '<div class="meta">暂无告警。</div>';
}

function filteredUnits(snapshot) {
  const query = state.filters.deviceSearch.trim().toLowerCase();
  return (snapshot.units || []).filter((unit) => {
    const matchesQuery = !query || [unit.unit_id, unit.building_id, unit.household_type].some((value) => String(value ?? '').toLowerCase().includes(query));
    const risk = unit.risk_score >= 60 ? 'high' : unit.risk_score >= 35 ? 'medium' : 'low';
    const matchesRisk = state.filters.riskFilter === 'all' || state.filters.riskFilter === risk;
    return matchesQuery && matchesRisk;
  }).sort((a, b) => {
    if (state.filters.deviceSort === 'energy') return b.energy_today_kwh - a.energy_today_kwh;
    if (state.filters.deviceSort === 'alphabet') return a.unit_id.localeCompare(b.unit_id);
    return b.risk_score - a.risk_score;
  });
}

function renderDevices(snapshot) {
  $('unitGrid').innerHTML = filteredUnits(snapshot).map((item) => {
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

function renderInnovation(snapshot) {
  const units = snapshot.units || [];
  const orders = snapshot.work_orders || [];
  const correlatedUnits = units.filter((item) => {
    let signalCount = 0;
    if (item.gas_ppm >= 18) signalCount += 1;
    if (item.smoke_ppm >= 45) signalCount += 1;
    if (item.power_w >= 3500) signalCount += 1;
    if (item.water_leak) signalCount += 1;
    return signalCount >= 2;
  }).length;
  const elderlyCareOrders = orders.filter((item) => item.kind === 'elderly_care').length;
  const peakEnergyUnits = units.filter((item) => item.power_w >= 2800).length;
  const slaProtectedOrders = orders.filter((item) => ['assigned', 'processing', 'resolved'].includes(item.status)).length;

  const cards = [
    ['关联风险住户', correlatedUnits, '多信号联合判断'],
    ['高峰负载住户', peakEnergyUnits, '支持峰值抑制策略'],
    ['老人关怀工单', elderlyCareOrders, '主动关怀而非被动响应'],
    ['SLA 保护工单', slaProtectedOrders, '支持自动升级闭环'],
  ];

  $('innovationKpiGrid').innerHTML = cards.map(([label, value, desc]) => `
    <article class="kpi-card">
      <div class="label">${escapeHtml(label)}</div>
      <strong class="value">${escapeHtml(String(value))}</strong>
      <div class="delta">${escapeHtml(desc)}</div>
    </article>
  `).join('');

  $('innovationMetrics').innerHTML = `
    <article class="building-card">
      <div class="title">创新 1：告警关联闭环</div>
      <div class="meta">当前存在 ${correlatedUnits} 个住户同时触发 2 类以上风险信号，可显著降低单点误报。</div>
    </article>
    <article class="building-card">
      <div class="title">创新 2：分时能耗画像</div>
      <div class="meta">当前高负载住户 ${peakEnergyUnits} 户，可用于晚高峰柔性干预与节能策略建议。</div>
    </article>
    <article class="building-card">
      <div class="title">创新 3：老人户主动关怀</div>
      <div class="meta">当前老人关怀类工单 ${elderlyCareOrders} 条，系统将关怀逻辑纳入物业流转体系。</div>
    </article>
    <article class="building-card">
      <div class="title">闭环效率提升点</div>
      <div class="meta">当前已进入派单/处理/待闭环阶段的工单 ${slaProtectedOrders} 条，体现自动调度与 SLA 升级能力。</div>
    </article>
  `;
}

function renderSettings(snapshot) {
  $('settingSummary').innerHTML = `
    <div>模拟时间：${escapeHtml(snapshot.simulation.sim_time)}</div>
    <div>楼栋数：${escapeHtml(snapshot.building_cards.length)}</div>
    <div>工单总数：${escapeHtml(snapshot.work_orders.length)}</div>
    <div>告警总数：${escapeHtml(snapshot.alerts.length)}</div>
    <div>自动刷新：${state.autoRefresh ? '开启' : '关闭'}</div>
  `;
}

function renderPage(snapshot) {
  renderSessionCard();
  renderKpis(snapshot);
  renderTrend(snapshot);
  renderAlertTypeChart(snapshot);
  renderBuildingCards(snapshot);
  renderNotifications('notificationFeed', snapshot.notifications || []);
  renderWorkflow(snapshot);
  renderAlerts(snapshot);
  renderDevices(snapshot);
  renderInnovation(snapshot);
  renderSettings(snapshot);

  $('simStatusText').textContent = snapshot.simulation.paused ? '已暂停' : '实时运行';
  $('simTime').textContent = `模拟时间：${snapshot.simulation.sim_time} | 第 ${snapshot.simulation.tick_index} 轮`;
}

async function sendOrderAction(orderId, action) {
  const result = await postJson('/api/work-orders/action', {
    order_id: orderId,
    action,
    actor: state.user?.username || '前端调度员',
    note: `${state.user?.username || '前端调度员'} 执行 ${action}`,
  });
  if (!result.ok) {
    throw new Error(result.message || '工单操作失败');
  }
  await refreshSnapshot();
}

async function sendControl(action) {
  const result = await postJson('/api/sim/control', { action });
  if (!result.ok) {
    throw new Error(result.message || '模拟控制失败');
  }
  await refreshSnapshot();
}

function exportSnapshot() {
  if (!state.snapshot) return;
  const blob = new Blob([JSON.stringify(state.snapshot, null, 2)], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `snapshot-${Date.now()}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

async function logout() {
  try {
    await postJson('/api/auth/logout', {});
  } catch (error) {
    console.warn(error);
  } finally {
    clearSession();
    location.href = '/login.html';
  }
}

async function refreshSnapshot() {
  state.snapshot = await getJson('/api/snapshot');
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
    const control = event.target.closest('[data-control]');
    if (control) {
      sendControl(control.dataset.control).catch((error) => {
        window.alert(error.message);
      });
    }
  });
  document.body.addEventListener('click', (event) => {
    if (event.target.matches('[data-action="export"]')) exportSnapshot();
  });
  document.body.addEventListener('click', (event) => {
    if (event.target.matches('[data-action="logout"]')) {
      logout().catch(() => {});
    }
  });
  document.body.addEventListener('click', (event) => {
    const building = event.target.closest('[data-building-focus]');
    if (building) {
      state.filters.building = building.dataset.buildingFocus;
      switchView('workflow');
      if (state.snapshot) renderWorkflow(state.snapshot);
    }
  });
  document.body.addEventListener('click', (event) => {
    const alert = event.target.closest('[data-alert-order]');
    if (alert && alert.dataset.alertOrder) {
      state.selectedOrderId = alert.dataset.alertOrder;
      switchView('workflow');
      if (state.snapshot) renderWorkflow(state.snapshot);
    }
  });

  $('orderSearch').addEventListener('input', (event) => {
    if (!state.snapshot) return;
    state.filters.query = event.target.value;
    renderWorkflow(state.snapshot);
  });
  $('buildingFilter').addEventListener('change', (event) => {
    if (!state.snapshot) return;
    state.filters.building = event.target.value;
    renderWorkflow(state.snapshot);
  });
  $('statusFilter').addEventListener('change', (event) => {
    if (!state.snapshot) return;
    state.filters.status = event.target.value;
    renderWorkflow(state.snapshot);
  });
  $('autoRefreshSelect').addEventListener('change', (event) => {
    state.autoRefresh = event.target.value === 'on';
  });
  $('deviceSearch').addEventListener('input', (event) => {
    if (!state.snapshot) return;
    state.filters.deviceSearch = event.target.value;
    renderDevices(state.snapshot);
  });
  $('riskFilter').addEventListener('change', (event) => {
    if (!state.snapshot) return;
    state.filters.riskFilter = event.target.value;
    renderDevices(state.snapshot);
  });
  $('deviceSort').addEventListener('change', (event) => {
    if (!state.snapshot) return;
    state.filters.deviceSort = event.target.value;
    renderDevices(state.snapshot);
  });
  window.addEventListener('hashchange', () => switchView(location.hash.replace('#', '') || 'overview'));
}

async function ensureSession() {
  if (!getToken()) {
    redirectToLogin();
    return false;
  }
  const payload = await getJson('/api/auth/me');
  state.user = payload.user || null;
  renderSessionCard();
  return Boolean(state.user);
}

async function bootstrap() {
  const ok = await ensureSession();
  if (!ok) return;
  bindEvents();
  switchView(state.activeView);
  await refreshSnapshot();
  setInterval(() => {
    if (state.autoRefresh) {
      refreshSnapshot().catch(() => {});
    }
  }, 2500);
}

bootstrap().catch((error) => {
  console.error(error);
  document.body.insertAdjacentHTML('beforeend', `<pre style="padding:24px;color:#b91c1c">加载失败：${escapeHtml(error.message)}</pre>`);
});
