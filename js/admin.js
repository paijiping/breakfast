(() => {
  const content = document.querySelector("#admin-content");
  const dialog = document.querySelector("#editor-dialog");
  const editorContent = document.querySelector("#editor-content");
  const state = { tab: "orders", dashboardPeriod: "day", categories: [], products: [], orders: [] };
  const statusLabels = {
    new: "新訂單",
    preparing: "製作中",
    completed: "已完成",
    cancelled: "已取消"
  };
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[character]);
  const formatPrice = (amount) => `NT$ ${Number(amount).toLocaleString("zh-TW")}`;

  function imageUrl(image) {
    if (image.startsWith("https://")) return image;
    return `https://images.unsplash.com/${encodeURIComponent(image)}?auto=format&fit=crop&w=240&q=80`;
  }

  async function api(url, options = {}) {
    const response = await fetch(url, {
      credentials: "include",
      headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}) },
      ...options
    });
    if (response.status === 401) {
      window.location.replace("/admin/login");
      throw new Error("登入已逾時。");
    }
    const payload = response.status === 204 ? null : await response.json();
    if (!response.ok) throw new Error(payload?.detail || "操作失敗，請稍後重試。");
    return payload;
  }

  function announce(message) {
    document.querySelector(".toast-message")?.remove();
    const toast = document.createElement("div");
    toast.className = "toast-message";
    toast.setAttribute("role", "status");
    toast.textContent = message;
    document.body.append(toast);
    window.setTimeout(() => toast.remove(), 3200);
  }

  function showError(error) {
    if (error.message !== "登入已逾時。") {
      content.innerHTML = `<p class="admin-error" role="alert">${escapeHtml(error.message)}</p>`;
    }
  }

  async function refreshData() {
    const [menu, orders] = await Promise.all([
      api("/api/admin/menu"),
      api("/api/admin/orders")
    ]);
    state.categories = menu.categories;
    state.products = menu.products;
    state.orders = orders.orders;
    render();
  }

  function renderHeading(title, description, action = "") {
    return `<div class="admin-page-heading"><div><p class="admin-eyebrow">朝日早餐 / 店家管理</p><h1>${title}</h1><p>${description}</p></div><div class="admin-toolbar">${action}</div></div>`;
  }

  function renderDashboard() {
    const periods = AdminDashboard.calculateRevenue(state.orders);
    const labels = { day: "本日", week: "本週", month: "本月" };
    const selected = periods[state.dashboardPeriod];
    const maximum = Math.max(0, ...selected.buckets.map((bucket) => bucket.amount));
    const summaries = Object.entries(labels).map(([period, label]) => `
      <div class="revenue-summary"><span>${label}</span><strong>${formatPrice(periods[period].total)}</strong></div>
    `).join("");
    const controls = Object.entries(labels).map(([period, label]) => `
      <button type="button" data-action="dashboard-period" data-period="${period}" aria-pressed="${period === state.dashboardPeriod}">${label}</button>
    `).join("");
    const bars = selected.buckets.map((bucket) => `
      <li class="revenue-bar-item" aria-label="${escapeHtml(bucket.label)}：${formatPrice(bucket.amount)}">
        <div class="revenue-bar-track" aria-hidden="true"><div class="revenue-bar" style="height: ${maximum ? bucket.amount / maximum * 100 : 0}%"></div></div>
        <span class="revenue-bar-label">${escapeHtml(bucket.label)}</span>
        <span class="revenue-bar-value">${formatPrice(bucket.amount)}</span>
      </li>
    `).join("");
    return `${renderHeading("營收總覽", "已完成訂單金額，非已確認收款。依台灣時間及下單時間統計。", `<button class="admin-small-button" type="button" data-action="refresh">重新整理</button>`)}
      <div class="revenue-summaries">${summaries}</div>
      <section class="revenue-section" aria-labelledby="revenue-heading">
        <div class="revenue-chart-heading"><div><h2 id="revenue-heading">${labels[state.dashboardPeriod]}營收</h2><p>單位：新台幣</p></div><div class="revenue-periods" role="group" aria-label="營收期間">${controls}</div></div>
        ${maximum === 0 ? '<p class="revenue-empty">此期間尚無營收。</p>' : ""}
        <div class="revenue-chart-scroll" tabindex="0" aria-label="營收圖表，可水平捲動"><ul class="revenue-chart">${bars}</ul></div>
      </section>`;
  }

  function renderOrders() {
    const orders = state.orders;
    const cards = orders.length ? orders.map((order) => `
      <article class="order-panel">
        <div class="order-heading">
          <div>
            <p class="order-number">${escapeHtml(order.order_number)} <span class="state-label">${escapeHtml(statusLabels[order.status] || order.status)}</span></p>
            <p class="order-meta">桌號 ${escapeHtml(order.table_number)} · ${escapeHtml(new Date(order.created_at).toLocaleString("zh-TW"))} · 到店付款</p>
          </div>
          <strong class="order-total">${formatPrice(order.total_amount)}</strong>
        </div>
        <div class="order-items">${order.items.map((item) => `
          <div class="order-item"><span>${escapeHtml(item.product_name)} × ${item.quantity}</span><strong>${formatPrice(item.unit_price * item.quantity)}</strong>
          ${item.note ? `<small>備註：${escapeHtml(item.note)}</small>` : ""}</div>
        `).join("")}</div>
        <form class="order-status-form" data-order-id="${order.id}">
          <label class="sr-only" for="order-status-${order.id}">更新訂單狀態</label>
          <select id="order-status-${order.id}" name="status">${Object.entries(statusLabels).map(([value, label]) => `<option value="${value}" ${value === order.status ? "selected" : ""}>${label}</option>`).join("")}</select>
          <button class="admin-small-button" type="submit">更新狀態</button>
        </form>
      </article>
    `).join("") : `<div class="empty-state">目前沒有訂單。</div>`;
    return `${renderHeading("訂單", `${orders.length} 筆訂單`, `<label class="filter-control">狀態<select id="order-filter"><option value="all">全部</option>${Object.entries(statusLabels).map(([value, label]) => `<option value="${value}">${label}</option>`).join("")}</select></label><button class="admin-small-button" type="button" data-action="refresh">重新整理</button>`)}<div class="admin-list">${cards}</div>`;
  }

  function renderProducts() {
    const rows = state.products.length ? state.products.map((product) => `
      <article class="admin-row">
        <img class="admin-row-image" src="${escapeHtml(imageUrl(product.image))}" alt="" loading="lazy">
        <div><h2 class="admin-row-title">${escapeHtml(product.name)} <span class="state-label ${product.is_available ? "" : "is-off"}">${product.is_available ? "供應中" : "停售"}</span></h2>
          <p class="admin-row-meta">${escapeHtml(state.categories.find((category) => category.id === product.category_id)?.label || "分類已停用")} · ${formatPrice(product.price)} · ${escapeHtml(product.tag)}</p>
        </div>
        <div class="admin-row-actions"><button class="admin-small-button" type="button" data-action="edit-product" data-id="${escapeHtml(product.id)}">編輯</button><button class="admin-small-button" type="button" data-action="toggle-product" data-id="${escapeHtml(product.id)}">${product.is_available ? "停售" : "恢復供應"}</button></div>
      </article>
    `).join("") : `<div class="empty-state">尚未建立商品。</div>`;
    return `${renderHeading("商品", "維護商品資訊、價格與供應狀態。", `<button class="admin-primary-button" type="button" data-action="add-product">新增商品</button>`)}<div class="admin-list">${rows}</div>`;
  }

  function renderCategories() {
    const rows = state.categories.length ? state.categories.map((category) => `
      <article class="admin-row">
        <div class="admin-row-image category-mark" aria-hidden="true">分</div>
        <div><h2 class="admin-row-title">${escapeHtml(category.label)} <span class="state-label ${category.is_active ? "" : "is-off"}">${category.is_active ? "啟用" : "停用"}</span></h2>
          <p class="admin-row-meta">排序 ${category.sort_order} · ${state.products.filter((product) => product.category_id === category.id).length} 項商品</p>
        </div>
        <div class="admin-row-actions"><button class="admin-small-button" type="button" data-action="edit-category" data-id="${escapeHtml(category.id)}">編輯</button><button class="admin-small-button" type="button" data-action="toggle-category" data-id="${escapeHtml(category.id)}">${category.is_active ? "停用" : "啟用"}</button></div>
      </article>
    `).join("") : `<div class="empty-state">尚未建立分類。</div>`;
    return `${renderHeading("分類", "分類停用後不會出現在顧客菜單。", `<button class="admin-primary-button" type="button" data-action="add-category">新增分類</button>`)}<div class="admin-list">${rows}</div>`;
  }

  function render() {
    document.querySelectorAll("[data-tab]").forEach((button) => {
      button.setAttribute("aria-current", button.dataset.tab === state.tab ? "page" : "false");
    });
    content.setAttribute("aria-busy", "false");
    content.innerHTML = state.tab === "dashboard" ? renderDashboard() : state.tab === "orders" ? renderOrders() : state.tab === "products" ? renderProducts() : renderCategories();
    if (state.tab === "dashboard") {
      const localNow = new Date(Date.now() + 8 * 60 * 60 * 1000);
      const currentIndex = state.dashboardPeriod === "day" ? localNow.getUTCHours()
        : state.dashboardPeriod === "week" ? (localNow.getUTCDay() + 6) % 7 : localNow.getUTCDate() - 1;
      const chart = content.querySelector(".revenue-chart-scroll");
      const currentBar = chart.querySelectorAll(".revenue-bar-item")[currentIndex];
      if (currentBar) {
        chart.scrollLeft += currentBar.getBoundingClientRect().left - chart.getBoundingClientRect().left
          - (chart.clientWidth - currentBar.clientWidth) / 2;
      }
    }
  }

  function field(label, name, value, options = {}) {
    const id = `field-${name}`;
    const input = options.multiline
      ? `<textarea id="${id}" name="${name}" ${options.required ? "required" : ""}>${escapeHtml(value)}</textarea>`
      : `<input id="${id}" name="${name}" value="${escapeHtml(value)}" type="${options.type || "text"}" ${options.required ? "required" : ""} ${options.min !== undefined ? `min="${options.min}"` : ""} ${options.step ? `step="${options.step}"` : ""} ${options.maxLength ? `maxlength="${options.maxLength}"` : ""}>`;
    return `<div class="editor-field ${options.wide ? "is-wide" : ""}"><label for="${id}">${label}</label>${input}</div>`;
  }

  function openCategoryEditor(category = null) {
    editorContent.innerHTML = `
      <h2 class="editor-heading">${category ? "編輯分類" : "新增分類"}</h2>
      <form id="entity-form" class="editor-form" data-kind="category" data-id="${escapeHtml(category?.id || "")}">
        ${field("分類名稱", "label", category?.label || "", { required: true, maxLength: 80, wide: true })}
        ${field("排序", "sort_order", category?.sort_order ?? 0, { type: "number", min: 0, step: 1, required: true })}
        <label class="editor-check"><input name="is_active" type="checkbox" ${category?.is_active === false || category?.is_active === 0 ? "" : "checked"}>分類啟用</label>
        <div class="editor-actions"><button class="admin-secondary-button" type="button" data-action="close-editor">取消</button><button class="admin-primary-button" type="submit">儲存分類</button></div>
      </form>`;
    dialog.showModal();
  }

  function openProductEditor(product = null) {
    const categoryOptions = state.categories.map((category) => `<option value="${escapeHtml(category.id)}" ${category.id === product?.category_id ? "selected" : ""}>${escapeHtml(category.label)}${category.is_active ? "" : "（停用）"}</option>`).join("");
    editorContent.innerHTML = `
      <h2 class="editor-heading">${product ? "編輯商品" : "新增商品"}</h2>
      <form id="entity-form" class="editor-form" data-kind="product" data-id="${escapeHtml(product?.id || "")}">
        <div class="editor-field"><label for="field-category_id">所屬分類</label><select id="field-category_id" name="category_id" required>${categoryOptions}</select></div>
        ${field("商品名稱", "name", product?.name || "", { required: true, maxLength: 100 })}
        ${field("價格（元）", "price", product?.price ?? "", { type: "number", min: 0, step: 1, required: true })}
        ${field("標籤", "tag", product?.tag || "", { maxLength: 80 })}
        ${field("商品介紹", "description", product?.description || "", { multiline: true, maxLength: 500, wide: true })}
        ${field("圖片 HTTPS 網址", "image", product?.image || "", { required: true, maxLength: 2048, wide: true })}
        ${field("圖片裁切位置", "image_position", product?.image_position || "center", { maxLength: 100 })}
        ${field("排序", "sort_order", product?.sort_order ?? 0, { type: "number", min: 0, step: 1, required: true })}
        <label class="editor-check"><input name="is_available" type="checkbox" ${product?.is_available === false || product?.is_available === 0 ? "" : "checked"}>商品供應中</label>
        ${product?.image?.startsWith("https://") ? `<img id="image-preview" class="editor-preview is-wide" src="${escapeHtml(product.image)}" alt="商品圖片預覽">` : `<p class="admin-row-meta is-wide">既有 Unsplash 圖片識別碼可保留；新圖片請填 HTTPS 網址。</p>`}
        <div class="editor-actions"><button class="admin-secondary-button" type="button" data-action="close-editor">取消</button><button class="admin-primary-button" type="submit">儲存商品</button></div>
      </form>`;
    dialog.showModal();
  }

  async function saveOrderStatus(form) {
    const orderId = form.dataset.orderId;
    const status = new FormData(form).get("status");
    try {
      await api(`/api/admin/orders/${orderId}`, { method: "PATCH", body: JSON.stringify({ status }) });
      await refreshData();
      announce("訂單狀態已更新。");
    } catch (error) {
      showError(error);
    }
  }

  async function saveEntity(form) {
    const kind = form.dataset.kind;
    const id = form.dataset.id;
    const formData = new FormData(form);
    let payload;
    let endpoint;
    if (kind === "category") {
      payload = {
        label: formData.get("label"),
        sort_order: Number(formData.get("sort_order")),
        is_active: form.elements.is_active.checked
      };
      endpoint = id ? `/api/admin/categories/${encodeURIComponent(id)}` : "/api/admin/categories";
    } else {
      payload = {
        category_id: formData.get("category_id"),
        name: formData.get("name"),
        description: formData.get("description"),
        price: Number(formData.get("price")),
        tag: formData.get("tag"),
        image: formData.get("image").trim(),
        image_position: formData.get("image_position"),
        sort_order: Number(formData.get("sort_order")),
        is_available: form.elements.is_available.checked
      };
      const existing = state.products.find((product) => product.id === id);
      const legacyImageUnchanged = existing && payload.image === existing.image && payload.image.startsWith("photo-");
      if (!payload.image.startsWith("https://") && !legacyImageUnchanged) {
        announce("新圖片請使用 HTTPS 網址。");
        return;
      }
      endpoint = id ? `/api/admin/products/${encodeURIComponent(id)}` : "/api/admin/products";
    }

    try {
      await api(endpoint, { method: id ? "PATCH" : "POST", body: JSON.stringify(payload) });
      dialog.close();
      await refreshData();
      announce("資料已儲存。");
    } catch (error) {
      announce(error.message);
    }
  }

  async function toggleEntity(kind, id) {
    try {
      if (kind === "product") {
        const product = state.products.find((item) => item.id === id);
        await api(`/api/admin/products/${encodeURIComponent(id)}`, {
          method: "PATCH", body: JSON.stringify({ is_available: !Boolean(product.is_available) })
        });
      } else {
        const category = state.categories.find((item) => item.id === id);
        await api(`/api/admin/categories/${encodeURIComponent(id)}`, {
          method: "PATCH", body: JSON.stringify({ is_active: !Boolean(category.is_active) })
        });
      }
      await refreshData();
      announce("供應狀態已更新。");
    } catch (error) {
      showError(error);
    }
  }

  document.addEventListener("click", async (event) => {
    const tab = event.target.closest("[data-tab]");
    if (tab) {
      state.tab = tab.dataset.tab;
      render();
      return;
    }
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const { action, id } = button.dataset;
    if (action === "refresh") {
      try { await refreshData(); } catch (error) { showError(error); }
    } else if (action === "dashboard-period") {
      state.dashboardPeriod = button.dataset.period;
      render();
      content.querySelector(`[data-period="${state.dashboardPeriod}"]`).focus();
    } else if (action === "add-category") openCategoryEditor();
    else if (action === "edit-category") openCategoryEditor(state.categories.find((item) => item.id === id));
    else if (action === "toggle-category") await toggleEntity("category", id);
    else if (action === "add-product") {
      if (state.categories.length) openProductEditor();
      else announce("請先建立分類。");
    } else if (action === "edit-product") openProductEditor(state.products.find((item) => item.id === id));
    else if (action === "toggle-product") await toggleEntity("product", id);
    else if (action === "close-editor") dialog.close();
  });

  content.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    if (form.matches(".order-status-form")) await saveOrderStatus(form);
  });

  editorContent.addEventListener("submit", async (event) => {
    if (!event.target.matches("#entity-form")) return;
    event.preventDefault();
    await saveEntity(event.target);
  });

  document.querySelector("#logout-button").addEventListener("click", async () => {
    try {
      await api("/api/admin/session", { method: "DELETE" });
      window.location.replace("/admin/login");
    } catch (error) {
      showError(error);
    }
  });

  content.addEventListener("change", (event) => {
    if (event.target.id !== "order-filter") return;
    const selectedStatus = event.target.value;
    content.querySelectorAll(".order-panel").forEach((panel) => {
      const orderId = Number(panel.querySelector(".order-status-form").dataset.orderId);
      const order = state.orders.find((item) => item.id === orderId);
      panel.hidden = selectedStatus !== "all" && order?.status !== selectedStatus;
    });
  });

  async function initialize() {
    try {
      await api("/api/admin/session");
      await refreshData();
    } catch (error) {
      showError(error);
    }
  }

  initialize();
})();