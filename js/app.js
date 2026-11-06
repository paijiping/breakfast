(() => {
  const elements = {
    categoryNav: document.querySelector("#category-nav"),
    productGrid: document.querySelector("#product-grid"),
    menuCount: document.querySelector("#menu-count"),
    search: document.querySelector("#menu-search"),
    tableButton: document.querySelector("#table-button"),
    tableLabel: document.querySelector("#table-label"),
    tableDialog: document.querySelector("#table-dialog"),
    tableInput: document.querySelector("#table-input"),
    tableForm: document.querySelector("#table-form"),
    tableMessage: document.querySelector("#table-dialog-message"),
    cartList: document.querySelector("#cart-list"),
    cartEmpty: document.querySelector("#cart-empty"),
    cartCount: document.querySelector("#cart-count"),
    cartTotal: document.querySelector("#cart-total"),
    checkoutButton: document.querySelector("#checkout-button"),
    mobileCartBar: document.querySelector("#mobile-cart-bar"),
    mobileCartButton: document.querySelector("#mobile-cart-button"),
    mobileCartCount: document.querySelector("#mobile-cart-count"),
    mobileCartTotal: document.querySelector("#mobile-cart-total"),
    cartDialog: document.querySelector("#cart-dialog"),
    mobileCartList: document.querySelector("#mobile-cart-list"),
    mobileCartEmpty: document.querySelector("#mobile-cart-empty"),
    mobileDialogTotal: document.querySelector("#mobile-dialog-total"),
    mobileCheckoutButton: document.querySelector("#mobile-checkout-button"),
    productDialog: document.querySelector("#product-dialog"),
    productDialogContent: document.querySelector("#product-dialog-content"),
    checkoutDialog: document.querySelector("#checkout-dialog"),
    checkoutContent: document.querySelector("#checkout-content")
  };

  let categories = [];
  let products = [];
  let activeCategory = "popular";
  let searchTerm = "";
  let selectedProduct = null;
  let selectedQuantity = 1;
  let tableNumber = new URLSearchParams(window.location.search).get("table")?.trim() || "";
  let isSubmitting = false;
  const MAX_ORDER_LINES = 50;
  const MAX_ITEM_QUANTITY = 99;
  const cart = [];

  const formatPrice = (amount) => `NT$ ${amount.toLocaleString("zh-TW")}`;
  const imageUrl = (id, width = 720) => `https://images.unsplash.com/${id}?auto=format&fit=crop&w=${width}&q=82`;
  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[character]);

  function renderCategories() {
    elements.categoryNav.innerHTML = categories.map((category) => `
      <button class="category-button" type="button" data-category="${category.id}" aria-pressed="${category.id === activeCategory}">
        ${category.label}
      </button>
    `).join("");
  }

  function renderMenu() {
    const visibleProducts = products.filter((product) => {
      const inCategory = activeCategory === "all" || product.category === activeCategory;
      const searchable = `${product.name} ${product.description} ${product.tag}`.toLocaleLowerCase("zh-TW");
      return inCategory && searchable.includes(searchTerm.toLocaleLowerCase("zh-TW"));
    });

    elements.menuCount.textContent = `共 ${visibleProducts.length} 樣餐點`;
    if (visibleProducts.length === 0) {
      elements.productGrid.innerHTML = `<div class="empty-results">${products.length ? "沒有找到符合的餐點，試試其他關鍵字。" : "目前沒有供應中的餐點。"}</div>`;
      return;
    }

    elements.productGrid.innerHTML = visibleProducts.map((product) => `
      <article class="product-card">
        <img class="product-image" src="${imageUrl(product.image)}" alt="${escapeHtml(product.name)}" loading="lazy" style="object-position:${escapeHtml(product.imagePosition)}" onerror="this.src='https://images.unsplash.com/photo-1490645935967-10de6ba17061?auto=format&fit=crop&w=720&q=82'">
        <div class="product-info">
          <div class="product-title-row">
            <h3 class="product-title">${escapeHtml(product.name)}</h3>
            <span class="product-price">${formatPrice(product.price)}</span>
          </div>
          <p class="product-description">${escapeHtml(product.description)}</p>
          <div class="product-card-bottom">
            <span class="product-tag">${escapeHtml(product.tag)}</span>
            <button class="select-button" type="button" data-product="${escapeHtml(product.id)}" aria-label="選擇${escapeHtml(product.name)}">
              選擇 <span class="select-plus" aria-hidden="true">+</span>
            </button>
          </div>
        </div>
      </article>
    `).join("");
  }

  function renderCartList(container) {
    container.innerHTML = cart.map((item, index) => `
      <div class="cart-line">
        <div class="cart-line-main">
          <p class="cart-line-name">${escapeHtml(item.name)}</p>
          ${item.note ? `<p class="cart-line-note">備註：${escapeHtml(item.note)}</p>` : ""}
          <div class="quantity-control" aria-label="${escapeHtml(item.name)}數量">
            <button type="button" data-cart-action="decrease" data-index="${index}" aria-label="減少${escapeHtml(item.name)}">−</button>
            <span>${item.quantity}</span>
            <button type="button" data-cart-action="increase" data-index="${index}" aria-label="增加${escapeHtml(item.name)}" ${item.quantity >= MAX_ITEM_QUANTITY ? "disabled" : ""}>+</button>
          </div>
        </div>
        <span class="cart-line-price">${formatPrice(item.price * item.quantity)}</span>
        <button class="remove-button" type="button" data-cart-action="remove" data-index="${index}">移除</button>
      </div>
    `).join("");
  }

  function renderCart() {
    const quantity = cart.reduce((sum, item) => sum + item.quantity, 0);
    const total = cart.reduce((sum, item) => sum + item.price * item.quantity, 0);
    const isEmpty = cart.length === 0;
    elements.cartCount.textContent = quantity;
    elements.cartTotal.textContent = formatPrice(total);
    elements.cartEmpty.hidden = !isEmpty;
    elements.cartList.hidden = isEmpty;
    elements.checkoutButton.disabled = isEmpty || isSubmitting;
    elements.mobileCartBar.hidden = isEmpty;
    elements.mobileCartCount.textContent = quantity;
    elements.mobileCartTotal.textContent = formatPrice(total);
    elements.mobileCartEmpty.hidden = !isEmpty;
    elements.mobileCartList.hidden = isEmpty;
    elements.mobileDialogTotal.textContent = formatPrice(total);
    elements.mobileCheckoutButton.disabled = isEmpty || isSubmitting;
    renderCartList(elements.cartList);
    renderCartList(elements.mobileCartList);
  }

  function showTableDialog(message = "掃描桌邊 QR code 通常會自動帶入桌號，也可以手動輸入。") {
    elements.tableMessage.textContent = message;
    elements.tableInput.value = tableNumber;
    elements.tableDialog.showModal();
    window.setTimeout(() => elements.tableInput.focus(), 0);
  }

  function updateTableLabel() {
    elements.tableLabel.textContent = tableNumber ? `桌號 ${tableNumber}` : "設定桌號";
  }

  function openProduct(productId) {
    selectedProduct = products.find((product) => product.id === productId);
    if (!selectedProduct) return;
    selectedQuantity = 1;
    elements.productDialogContent.innerHTML = `
      <img class="product-dialog-image" src="${imageUrl(selectedProduct.image, 900)}" alt="${escapeHtml(selectedProduct.name)}" onerror="this.src='https://images.unsplash.com/photo-1490645935967-10de6ba17061?auto=format&fit=crop&w=900&q=82'">
      <div class="product-dialog-inner">
        <div class="product-dialog-title-row"><h2 id="product-dialog-title">${escapeHtml(selectedProduct.name)}</h2><strong>${formatPrice(selectedProduct.price)}</strong></div>
        <p>${escapeHtml(selectedProduct.description)}</p>
        <label class="dialog-label" for="product-note">餐點備註（選填）</label>
        <textarea class="product-note" id="product-note" maxlength="80" placeholder="例如：吐司不烤、醬少一點"></textarea>
        <p class="submit-error" id="product-quantity-error" role="alert" hidden></p>
        <div class="product-dialog-actions">
          <div class="quantity-control" aria-label="餐點數量">
            <button type="button" data-product-quantity="decrease" aria-label="減少數量" disabled>−</button>
            <span id="selected-quantity">1</span>
            <button type="button" data-product-quantity="increase" aria-label="增加數量">+</button>
          </div>
          <button class="primary-button" id="add-product-button" type="button"><span>加入餐點</span><span>${formatPrice(selectedProduct.price)}</span></button>
        </div>
      </div>
    `;
    elements.productDialog.showModal();
  }

  function addSelectedProduct() {
    const note = elements.productDialogContent.querySelector("#product-note").value.trim();
    const error = elements.productDialogContent.querySelector("#product-quantity-error");
    error.hidden = true;
    error.textContent = "";
    const existing = cart.find((item) => item.id === selectedProduct.id && item.note === note);
    if (existing && existing.quantity + selectedQuantity > MAX_ITEM_QUANTITY) {
      error.textContent = `同一餐點與備註的數量上限為 ${MAX_ITEM_QUANTITY}，請先調整購物車中的數量。`;
      error.hidden = false;
      return;
    }
    if (!existing && cart.length >= MAX_ORDER_LINES) {
      error.textContent = `每筆訂單最多 ${MAX_ORDER_LINES} 個餐點明細，請先調整購物車。`;
      error.hidden = false;
      return;
    }
    if (existing) existing.quantity += selectedQuantity;
    else cart.push({ ...selectedProduct, quantity: selectedQuantity, note });
    elements.productDialog.close();
    renderCart();
  }

  function updateCartItem(action, index) {
    const item = cart[index];
    if (!item) return;
    if (action === "increase" && item.quantity < MAX_ITEM_QUANTITY) item.quantity += 1;
    if (action === "decrease") item.quantity -= 1;
    if (action === "remove" || item.quantity <= 0) cart.splice(index, 1);
    renderCart();
  }

  function openCheckout() {
    if (cart.length === 0) return;
    if (!tableNumber) {
      elements.cartDialog.close();
      showTableDialog("送出前請先設定內用桌號。掃描桌邊 QR code 通常會自動帶入，也可以手動輸入。");
      return;
    }

    const total = cart.reduce((sum, item) => sum + item.price * item.quantity, 0);
    elements.checkoutContent.innerHTML = `
      <p class="eyebrow">ORDER SUMMARY</p>
      <h2 id="checkout-heading">確認這份早餐</h2>
      <div class="checkout-table"><span>內用桌號</span><span>${escapeHtml(tableNumber)}</span></div>
      <div class="checkout-lines">${cart.map((item) => `
        <div class="checkout-line"><span>${escapeHtml(item.name)} × ${item.quantity}${item.note ? `<small>備註：${escapeHtml(item.note)}</small>` : ""}</span><strong>${formatPrice(item.price * item.quantity)}</strong></div>
      `).join("")}</div>
      <div class="checkout-total"><span>總計</span><strong>${formatPrice(total)}</strong></div>
      <p class="checkout-payment">到店付款・內用</p>
      <button class="primary-button" id="submit-order-button" type="button"><span>送出訂單</span><span aria-hidden="true">→</span></button>
      <button class="checkout-cancel" id="checkout-cancel" type="button">返回修改餐點</button>
    `;
    elements.cartDialog.close();
    elements.checkoutDialog.showModal();
  }

  async function submitOrder() {
    if (isSubmitting || cart.length === 0 || !tableNumber) return;
    isSubmitting = true;
    const button = elements.checkoutContent.querySelector("#submit-order-button");
    button.disabled = true;
    button.innerHTML = "<span>訂單送出中…</span><span aria-hidden=\"true\">…</span>";
    const order = {
      table: tableNumber,
      items: cart.map(({ id, quantity, note }) => ({ id, quantity, note }))
    };

    try {
      const result = await window.breakfastOrderSubmission.submit(order);
      cart.splice(0, cart.length);
      isSubmitting = false;
      renderCart();
      elements.checkoutContent.innerHTML = `
        <p class="eyebrow">ORDER CONFIRMED</p>
        <h2 id="checkout-heading">訂單已送出</h2>
        <div class="demo-result"><span class="demo-result-mark" aria-hidden="true">✓</span><p>訂單編號</p><strong>${escapeHtml(result.orderId)}</strong></div>
        <p class="checkout-payment">桌號 ${escapeHtml(result.table)}・到店付款・總計 ${formatPrice(result.total)}</p>
        <button class="primary-button" id="finish-order-button" type="button"><span>回到菜單</span><span aria-hidden="true">→</span></button>
      `;
    } catch (error) {
      isSubmitting = false;
      renderCart();
      const errorMessage = document.createElement("p");
      errorMessage.className = "submit-error";
      errorMessage.setAttribute("role", "alert");
      errorMessage.textContent = error.message || "送出失敗，請再試一次。";
      elements.checkoutContent.prepend(errorMessage);
      const retryButton = elements.checkoutContent.querySelector("#submit-order-button");
      if (retryButton) {
        retryButton.disabled = false;
        retryButton.querySelector("span:first-child").textContent = "重試送出";
      }
    }
  }

  elements.categoryNav.addEventListener("click", (event) => {
    const button = event.target.closest("[data-category]");
    if (!button) return;
    activeCategory = button.dataset.category;
    renderCategories();
    renderMenu();
  });

  elements.productGrid.addEventListener("click", (event) => {
    const button = event.target.closest("[data-product]");
    if (button) openProduct(button.dataset.product);
  });

  elements.search.addEventListener("input", () => {
    searchTerm = elements.search.value.trim();
    if (searchTerm) activeCategory = "all";
    else if (activeCategory === "all") activeCategory = "popular";
    renderCategories();
    renderMenu();
  });

  elements.search.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      elements.search.value = "";
      searchTerm = "";
      activeCategory = "popular";
      renderCategories();
      renderMenu();
      elements.search.blur();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) {
      event.preventDefault();
      elements.search.focus();
    }
  });

  elements.tableButton.addEventListener("click", () => showTableDialog());
  elements.tableForm.addEventListener("submit", (event) => {
    event.preventDefault();
    tableNumber = elements.tableInput.value.trim();
    if (!tableNumber) return;
    updateTableLabel();
    const url = new URL(window.location.href);
    url.searchParams.set("table", tableNumber);
    window.history.replaceState({}, "", url);
    elements.tableDialog.close();
  });

  elements.productDialogContent.addEventListener("click", (event) => {
    const quantityButton = event.target.closest("[data-product-quantity]");
    if (quantityButton) {
      const direction = quantityButton.dataset.productQuantity === "increase" ? 1 : -1;
      selectedQuantity = Math.min(MAX_ITEM_QUANTITY, Math.max(1, selectedQuantity + direction));
      elements.productDialogContent.querySelector("#selected-quantity").textContent = selectedQuantity;
      elements.productDialogContent.querySelector("#add-product-button span:last-child").textContent = formatPrice(selectedProduct.price * selectedQuantity);
      elements.productDialogContent.querySelector('[data-product-quantity="decrease"]').disabled = selectedQuantity === 1;
      elements.productDialogContent.querySelector('[data-product-quantity="increase"]').disabled = selectedQuantity === MAX_ITEM_QUANTITY;
    }
    if (event.target.closest("#add-product-button")) addSelectedProduct();
  });

  [elements.cartList, elements.mobileCartList].forEach((list) => {
    list.addEventListener("click", (event) => {
      const button = event.target.closest("[data-cart-action]");
      if (button) updateCartItem(button.dataset.cartAction, Number(button.dataset.index));
    });
  });

  elements.checkoutButton.addEventListener("click", openCheckout);
  elements.mobileCartButton.addEventListener("click", () => elements.cartDialog.showModal());
  elements.mobileCheckoutButton.addEventListener("click", openCheckout);
  elements.checkoutContent.addEventListener("click", (event) => {
    if (event.target.closest("#submit-order-button")) submitOrder();
    if (event.target.closest("#checkout-cancel")) elements.checkoutDialog.close();
    if (event.target.closest("#finish-order-button")) elements.checkoutDialog.close();
  });

  renderCart();
  updateTableLabel();

  async function loadMenu() {
    elements.productGrid.setAttribute("aria-busy", "true");
    elements.menuCount.textContent = "正在載入菜單…";
    elements.productGrid.innerHTML = '<p class="menu-loading">正在連線取得最新菜單…</p>';
    try {
      const menu = await window.breakfastMenuApi.load();
      categories = menu.categories;
      products = menu.products;
      if (!categories.some((category) => category.id === activeCategory)) {
        activeCategory = categories[0]?.id || "all";
      }
      elements.productGrid.setAttribute("aria-busy", "false");
      renderCategories();
      renderMenu();
    } catch (error) {
      elements.menuCount.textContent = "菜單暫時無法載入";
      elements.productGrid.setAttribute("aria-busy", "false");
      elements.productGrid.innerHTML = `
        <div class="menu-error" role="alert">
          <p>${escapeHtml(error.message || "連線失敗，請稍後重試。")}</p>
          <button class="select-button" id="retry-menu-button" type="button">重新載入</button>
        </div>
      `;
    }
  }

  elements.productGrid.addEventListener("click", (event) => {
    if (event.target.closest("#retry-menu-button")) loadMenu();
  });

  loadMenu();
  if (!tableNumber) window.setTimeout(() => showTableDialog(), 350);
})();