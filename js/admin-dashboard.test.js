const test = require("node:test");
const assert = require("node:assert/strict");
const { calculateRevenue } = require("./admin-dashboard.js");

test("依台灣時間及已完成狀態計算當日、本週和本月", () => {
  const orders = [
    { status: "completed", total_amount: 100, created_at: "2024-03-03T16:00:00Z" },
    { status: "completed", total_amount: 50, created_at: "2024-03-03T15:59:59Z" },
    { status: "completed", total_amount: 30, created_at: "2024-02-29T16:00:00Z" },
    { status: "completed", total_amount: 20, created_at: "2024-02-28T16:00:00Z" },
    { status: "completed", total_amount: 500, created_at: "2024-03-04T05:00:01Z" },
    { status: "new", total_amount: 600, created_at: "2024-03-04T00:00:00Z" },
    { status: "preparing", total_amount: 700, created_at: "2024-03-04T00:00:00Z" },
    { status: "cancelled", total_amount: 800, created_at: "2024-03-04T00:00:00Z" }
  ];
  const result = calculateRevenue(orders, new Date("2024-03-04T05:00:00Z"));
  assert.equal(result.day.total, 100);
  assert.equal(result.day.buckets[0].amount, 100);
  assert.equal(result.week.total, 100);
  assert.equal(result.week.buckets[0].amount, 100);
  assert.equal(result.month.total, 180);
  assert.equal(result.month.buckets[0].amount, 30);
  assert.equal(result.month.buckets[2].amount, 50);
  for (const period of Object.values(result)) {
    assert.equal(period.buckets.reduce((sum, bucket) => sum + bucket.amount, 0), period.total);
  }
});

test("週一跨年、閏月及空資料", () => {
  const yearBoundary = calculateRevenue([
    { status: "completed", total_amount: 42, created_at: "2023-12-31T16:00:00Z" },
    { status: "completed", total_amount: 80, created_at: "2023-12-31T15:59:59Z" }
  ], new Date("2024-01-01T04:00:00Z"));
  assert.equal(yearBoundary.week.total, 42);
  assert.equal(yearBoundary.month.total, 42);
  const leapMonth = calculateRevenue([], new Date("2024-02-29T10:00:00Z"));
  assert.equal(leapMonth.month.buckets.length, 29);
  assert.equal(leapMonth.day.total, 0);
  assert.equal(leapMonth.week.total, 0);
  assert.equal(leapMonth.month.total, 0);
});

test("本週可跨月，並略過無效或未來的時間", () => {
  const result = calculateRevenue([
    { status: "completed", total_amount: 60, created_at: "2024-04-29T16:00:00Z" },
    { status: "completed", total_amount: 25, created_at: "2024-05-01T16:00:00Z" },
    { status: "completed", total_amount: 99, created_at: "invalid" },
    { status: "completed", total_amount: 99, created_at: "2024-05-02T04:00:01Z" }
  ], new Date("2024-05-02T04:00:00Z"));
  assert.equal(result.week.total, 85);
  assert.equal(result.month.total, 25);
  assert.equal(result.day.total, 25);
});