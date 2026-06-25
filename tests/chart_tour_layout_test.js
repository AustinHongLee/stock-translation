const assert = require("node:assert/strict");
const { scoreCalloutGeometry } = require("../app/ui/static/chart_tour.js");

const bounds = {
  left: 0,
  right: 900,
  top: 0,
  bottom: 520,
  recentLeft: 560,
  futureLeft: 790,
  bottomControlTop: 430,
};

const anchorPoint = { x: 710, y: 220 };
const recentCandles = Array.from({ length: 45 }, (_, index) => ({
  x: 585 + index * 7,
  y: 150 + (index % 5) * 6,
  width: 5,
  height: 116,
  close: { x: 587 + index * 7, y: 205 + (index % 4) * 5 },
  recent: true,
}));

const coveringRecentCandles = { x: 570, y: 130, width: 300, height: 178 };
const avoidingRecentCandles = { x: 40, y: 38, width: 220, height: 92 };
assert(
  scoreCalloutGeometry(coveringRecentCandles, anchorPoint, recentCandles, [], null, bounds) >
    scoreCalloutGeometry(avoidingRecentCandles, anchorPoint, recentCandles, [], null, bounds),
  "candidate covering the latest 45 candles should score worse than a clear candidate",
);

const bottomControlOverlap = { x: 86, y: 432, width: 220, height: 82 };
const clearUpperArea = { x: 86, y: 278, width: 220, height: 82 };
assert(
  scoreCalloutGeometry(bottomControlOverlap, anchorPoint, [], [], null, bounds) >
    scoreCalloutGeometry(clearUpperArea, anchorPoint, [], [], null, bounds),
  "candidate entering the bottom tour controls should receive a penalty",
);
