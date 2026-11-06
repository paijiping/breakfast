window.breakfastMenuApi = {
  async load() {
    const response = await fetch("/api/menu", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("菜單載入失敗，請稍後重試。");
    return response.json();
  }
};