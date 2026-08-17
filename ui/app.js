const apiKeyMeta = document.querySelector('meta[name="api-key"]');
const apiKey = apiKeyMeta ? apiKeyMeta.content : "";

// --- Three.js Scene Setup ---
const container = document.getElementById("webgl-container");
const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x000408, 0.04);

const camera = new THREE.PerspectiveCamera(
  60,
  window.innerWidth / window.innerHeight,
  0.1,
  1000,
);
camera.position.set(0, 5, 15);
camera.lookAt(0, 0, 0);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(window.devicePixelRatio);
container.appendChild(renderer.domElement);

// --- Market Floor & Grid ---
const gridHelper = new THREE.GridHelper(100, 100, 0x00ffcc, 0x001a1a);
scene.add(gridHelper);

// --- Lighting ---
const ambientLight = new THREE.AmbientLight(0xffffff, 0.3);
scene.add(ambientLight);
const pointLight = new THREE.PointLight(0x00ffcc, 1, 50);
pointLight.position.set(0, 10, 0);
scene.add(pointLight);

// --- State Variables ---
let targetGridColor = new THREE.Color(0x00ffcc);
let currentGridColor = new THREE.Color(0x00ffcc);
let currentRegime = null;
let lastPing = Date.now();

let particleSystem = null;
let particleCount = 0;
let pVelocities = null;
let globalVolume = 0;

// --- Initialize Particles ---
const pGeo = new THREE.BufferGeometry();
particleCount = 5000;
const pPos = new Float32Array(particleCount * 3);
pVelocities = new Float32Array(particleCount * 3);

for (let i = 0; i < particleCount; i++) {
  pPos[i * 3] = (Math.random() - 0.5) * 40;
  pPos[i * 3 + 1] = (Math.random() - 0.5) * 20;
  pPos[i * 3 + 2] = (Math.random() - 0.5) * 40;
  pVelocities[i * 3] = (Math.random() - 0.5) * 0.05;
  pVelocities[i * 3 + 1] = (Math.random() - 0.5) * 0.05;
  pVelocities[i * 3 + 2] = (Math.random() - 0.5) * 0.05;
}
pGeo.setAttribute("position", new THREE.BufferAttribute(pPos, 3));
const pMat = new THREE.PointsMaterial({
  color: 0x00ffcc,
  size: 0.1,
  transparent: true,
  opacity: 0.6,
  blending: THREE.AdditiveBlending,
});
particleSystem = new THREE.Points(pGeo, pMat);
scene.add(particleSystem);

// --- Regime Color Mapping ---
const regimeColors = {
  TRENDING_UP: 0x00ffcc,
  TRENDING_DOWN: 0xffaa00,
  RANGING: 0x88cc88,
  VOLATILE_CRASH: 0xff0055,
  UNKNOWN: 0x00ffcc,
};

// --- CandleEngine ---
class CandleEngine {
  constructor(scene, maxCandles = 1000) {
    this.scene = scene;
    this.maxCandles = maxCandles;
    this.candles = []; // Store OHLCV data
    this.currentCandle = null;
    this.timeframeMs = 60000; // 1 minute candles

    // Setup InstancedMesh for bodies
    const bodyGeo = new THREE.BoxGeometry(0.8, 1, 0.8);
    this.bodyMat = new THREE.MeshLambertMaterial({ color: 0xffffff });
    this.bodyMesh = new THREE.InstancedMesh(
      bodyGeo,
      this.bodyMat,
      this.maxCandles,
    );
    this.bodyMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.scene.add(this.bodyMesh);

    // Setup InstancedMesh for wicks
    const wickGeo = new THREE.CylinderGeometry(0.05, 0.05, 1, 8);
    this.wickMat = new THREE.MeshLambertMaterial({ color: 0xffffff });
    this.wickMesh = new THREE.InstancedMesh(
      wickGeo,
      this.wickMat,
      this.maxCandles,
    );
    this.wickMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.scene.add(this.wickMesh);

    this.dummy = new THREE.Object3D();
    this.colorObj = new THREE.Color();
    this.upColor = new THREE.Color(0x00ffcc);
    this.downColor = new THREE.Color(0xff0055);

    this.priceScale = 0.05; // Scale down price for 3D space
    this.baseY = 0; // Baseline Y offset
  }

  processTick(tick) {
    const price = tick.price;
    const ts = tick.timestamp;

    // Group into timeframe
    const candleTime = Math.floor(ts / this.timeframeMs) * this.timeframeMs;

    if (!this.currentCandle || this.currentCandle.time !== candleTime) {
      // New candle
      if (this.currentCandle) {
        this.candles.push(this.currentCandle);
        if (this.candles.length > this.maxCandles) {
          this.candles.shift(); // Keep buffer size
        }
      }

      this.currentCandle = {
        time: candleTime,
        open: price,
        high: price,
        low: price,
        close: price,
        volume: tick.volume,
      };

      // Adjust baseline on first candle
      if (this.candles.length === 0) {
        this.baseY = price;
      }
    } else {
      // Update current candle
      this.currentCandle.high = Math.max(this.currentCandle.high, price);
      this.currentCandle.low = Math.min(this.currentCandle.low, price);
      this.currentCandle.close = price;
      this.currentCandle.volume += tick.volume;
    }

    this.updateMeshes();
  }

  updateMeshes() {
    // Render all historical candles + current
    const allCandles = [...this.candles];
    if (this.currentCandle) allCandles.push(this.currentCandle);

    const count = allCandles.length;

    // Reset counts
    this.bodyMesh.count = count;
    this.wickMesh.count = count;

    // Shift camera/scene offset so latest candle is near 0
    const xOffset = -(count * 1.5) + 10;

    for (let i = 0; i < count; i++) {
      const c = allCandles[i];

      // Determine color
      const isUp = c.close >= c.open;
      this.colorObj.copy(isUp ? this.upColor : this.downColor);

      // Calculate dimensions
      const bodyHeight = Math.max(
        Math.abs(c.close - c.open) * this.priceScale,
        0.01,
      ); // Min height
      const bodyY = ((c.open + c.close) / 2 - this.baseY) * this.priceScale;

      const wickHeight = (c.high - c.low) * this.priceScale;
      const wickY = ((c.high + c.low) / 2 - this.baseY) * this.priceScale;

      const xPos = xOffset + i * 1.5;

      if (viewMode === "HEATMAP") {
        // World-Class Feature 5: Quantum Liquidity Heatmap overlay
        // Heatmap view: Flat squares mapped to grid, color intensity based on volume
        const heatmapScale = Math.min((c.volume || 0.1) * 2, 5.0);
        this.dummy.position.set(xPos, 0, (i % 5) * 1.5); // Spread on Z axis
        this.dummy.scale.set(1.4, 0.1, 1.4);
        this.dummy.updateMatrix();
        this.bodyMesh.setMatrixAt(i, this.dummy.matrix);

        // Color based on volume intensity (brighter = more volume)
        const intensity = Math.min((c.volume || 0) / 10, 1.0);
        this.colorObj.setHSL(isUp ? 0.45 : 0.95, 1.0, 0.2 + intensity * 0.6);
        this.bodyMesh.setColorAt(i, this.colorObj);

        // Hide wicks
        this.dummy.scale.set(0, 0, 0);
        this.dummy.updateMatrix();
        this.wickMesh.setMatrixAt(i, this.dummy.matrix);
      } else {
        // Set Body Instance (City View)
        this.dummy.position.set(xPos, bodyY, 0);
        this.dummy.scale.set(1, bodyHeight, 1);
        this.dummy.updateMatrix();
        this.bodyMesh.setMatrixAt(i, this.dummy.matrix);
        this.bodyMesh.setColorAt(i, this.colorObj);

        // Set Wick Instance
        this.dummy.position.set(xPos, wickY, 0);
        this.dummy.scale.set(1, wickHeight, 1);
        this.dummy.updateMatrix();
        this.wickMesh.setMatrixAt(i, this.dummy.matrix);
        this.wickMesh.setColorAt(i, this.colorObj);
      }
    }

    if (this.bodyMesh) {
      try {
        if (this.bodyMesh.instanceMatrix)
          this.bodyMesh.instanceMatrix.needsUpdate = true;
        if (this.bodyMesh.instanceColor)
          this.bodyMesh.instanceColor.needsUpdate = true;
      } catch (e) {
        console.error("CandleEngine updateMeshes error:", e);
      }
    }
    if (this.wickMesh) {
      try {
        if (this.wickMesh.instanceMatrix)
          this.wickMesh.instanceMatrix.needsUpdate = true;
        if (this.wickMesh.instanceColor)
          this.wickMesh.instanceColor.needsUpdate = true;
      } catch (e) {
        console.error("CandleEngine updateMeshes error:", e);
      }
    }
  }
}

const candleEngine = new CandleEngine(scene, 1000);

// --- Lightweight Charts Init ---
const chartOptions = {
  layout: {
    textColor: "#00ffcc",
    background: { type: "solid", color: "transparent" },
  },
  grid: {
    vertLines: { color: "rgba(0, 255, 204, 0.1)" },
    horzLines: { color: "rgba(0, 255, 204, 0.1)" },
  },
  timeScale: {
    timeVisible: true,
    secondsVisible: false,
  },
};
const tvContainer = document.getElementById("tvchart");
let chart = null;
let candleSeries = null;

if (tvContainer) {
  try {
    chart = LightweightCharts.createChart(tvContainer, chartOptions);
    candleSeries = chart.addCandleSeries({
      upColor: "#00ffcc",
      downColor: "#ff0055",
      borderDownColor: "#ff0055",
      borderUpColor: "#00ffcc",
      wickDownColor: "#ff0055",
      wickUpColor: "#00ffcc",
    });
  } catch (e) {
    console.error("Chart initialization error:", e);
  }
} else {
  console.warn("tvchart container not found, skipping chart initialization");
}

// --- Helper Functions ---
function throttle(func, limit) {
  let lastFunc;
  let lastRan;
  return function (...args) {
    if (!lastRan) {
      requestAnimationFrame(() => {
        func.apply(this, args);
        lastRan = Date.now();
      });
    } else {
      clearTimeout(lastFunc);
      lastFunc = setTimeout(
        () => {
          if (Date.now() - lastRan >= limit) {
            requestAnimationFrame(() => {
              func.apply(this, args);
              lastRan = Date.now();
            });
          }
        },
        Math.max(limit - (Date.now() - lastRan), 0),
      );
    }
  };
}

function updateHUD(data, type) {
  try {
    // PERFORMANCE OPTIMIZATION: Use textContent over innerText
    // 💡 What: Replaced innerText with textContent.
    // 🎯 Why: innerText triggers a reflow (layout calculation) which is expensive, while textContent only updates the text nodes.
    // 📊 Impact: Significantly reduces layout thrashing and CPU load in the main thread during high-frequency WebSocket updates.
    // 🔬 Measurement: Observe reduced layout calculation time in Chrome DevTools Performance profile.
    if (type === "synthesis") {
      const el = document.getElementById("val-synthesis");
      if (el) el.textContent = `[COPILOT] ${data.text}`;
    } else if (type === "balance") {
      const balEl = document.getElementById("val-balance");
      if (balEl && data.balance !== undefined) {
        balEl.textContent = `$${data.balance.toFixed(2)}`;
      }

      const modeEl = document.getElementById("val-mode");
      if (modeEl && data.mode) {
        modeEl.textContent = data.mode === "LIVE" ? "LIVE WARNING" : "DRY RUN";
        modeEl.className = `mode-indicator mode-${data.mode}`;
      }
    } else if (type === "signal") {
      const regimeClass = `regime-${data.regime}`;

      const regimeEl = document.getElementById("val-regime");
      if (regimeEl && data.regime) {
        regimeEl.textContent = data.regime;
        regimeEl.className = `value ${regimeClass}`;
      }

      // Update 3D Floor & Lights based on regime
      if (data.regime) {
        targetGridColor.setHex(regimeColors[data.regime] || 0x00ffcc);
      }
    } else if (type === "metric") {
      if (data.key === "liquidity_velocity") {
        const vel = parseFloat(data.value);
        // Flash screen red if circuit breaker triggered (velocity < -50)
        if (vel < -50.0) {
          triggerTradeAlert("SELL"); // Flash red
          addLog(
            `[CRITICAL] LIQUIDITY VELOCITY CIRCUIT BREAKER TRIPPED! (${vel.toFixed(2)})`,
            "#ff0055",
          );
          showToast(
            `[CRITICAL] CIRCUIT BREAKER TRIPPED! (${vel.toFixed(2)})`,
            "error",
          );
        }
      }
    }
  } catch (e) {
    console.error("updateHUD error:", e);
  }
}

function triggerTradeAlert(action) {
  const overlay = document.getElementById("alert-overlay");
  if (!overlay) return;

  const baseClass =
    action === "BUY" ? "flash-buy" : action === "SELL" ? "flash-sell" : "";
  if (baseClass) {
    overlay.className = baseClass + " flash-active";

    // Force reflow
    void overlay.offsetWidth;

    overlay.className = baseClass + " flash-fade";
  }
}

function addLog(text, colorHex) {
  try {
    const logPanel = document.getElementById("log-panel");
    if (!logPanel) return;

    const entry = document.createElement("div");
    entry.className = "log-entry";
    entry.style.color = colorHex;
    entry.style.borderColor = colorHex;
    entry.textContent = text;
    logPanel.appendChild(entry);

    // Keep only the last 8 logs to prevent DOM bloat
    while (logPanel.children.length > 8) {
      logPanel.removeChild(logPanel.firstChild);
    }
  } catch (e) {
    console.error("addLog error:", e);
  }
}

// --- Handle Orderbook Depth Visuals ---
const renderOrderbook = throttle(function (data) {
  try {
    const asksContainer = document.getElementById("depth-asks");
    const bidsContainer = document.getElementById("depth-bids");
    if (!asksContainer || !bidsContainer) return;

    const asks = data.asks || [];
    const bids = data.bids || [];

    // Render top 5 asks
    let maxAskVol = 0.001;
    const numAsks = Math.min(asks.length, 5);
    for (let i = 0; i < numAsks; i++) {
      if (asks[i][1] > maxAskVol) maxAskVol = asks[i][1];
    }

    // PERFORMANCE OPTIMIZATION: Use DocumentFragment for batching DOM updates
    // 💡 What: Used DocumentFragment to batch DOM inserts instead of appending to DOM directly.
    // 🎯 Why: Reduces reflows/repaints, making the UI much more responsive during high-frequency orderbook updates.
    // PERFORMANCE OPTIMIZATION: Element cloning
    // 💡 What: Used cloneNode(true) instead of createElement in loops.
    // 🎯 Why: createElement is slower than cloneNode when repeatedly creating the same structure.

    // Create templates once
    const wrapperTemplate = document.createElement("div");
    wrapperTemplate.className = "ob-row-wrapper";
    const bgTemplateAsks = document.createElement("div");
    bgTemplateAsks.className = "ob-bg-ask-custom";
    const priceSpanTemplateAsks = document.createElement("span");
    priceSpanTemplateAsks.className = "ob-text-ask";
    const volSpanTemplate = document.createElement("span");
    volSpanTemplate.className = "ob-vol";

    wrapperTemplate.appendChild(bgTemplateAsks);
    wrapperTemplate.appendChild(priceSpanTemplateAsks);
    wrapperTemplate.appendChild(volSpanTemplate);

    const asksFragment = document.createDocumentFragment();
    for (let i = 0; i < numAsks; i++) {
      const reversedIndex = numAsks - 1 - i;
      const price = asks[reversedIndex][0];
      const vol = asks[reversedIndex][1];
      const pct = (vol / maxAskVol) * 100;

      const clone = wrapperTemplate.cloneNode(true);
      clone.children[0].style.width = pct + "%";
      clone.children[1].textContent = price.toFixed(1);
      clone.children[2].textContent = vol.toFixed(4);
      asksFragment.appendChild(clone);
    }
    asksContainer.textContent = "";
    asksContainer.appendChild(asksFragment);

    // Render top 5 bids
    let maxBidVol = 0.001;
    const numBids = Math.min(bids.length, 5);
    for (let i = 0; i < numBids; i++) {
      if (bids[i][1] > maxBidVol) maxBidVol = bids[i][1];
    }

    const bidsFragment = document.createDocumentFragment();
    const bgTemplateBids = document.createElement("div");
    bgTemplateBids.className = "ob-bg-bid-custom";
    const priceSpanTemplateBids = document.createElement("span");
    priceSpanTemplateBids.className = "ob-text-bid";

    const wrapperTemplateBids = document.createElement("div");
    wrapperTemplateBids.className = "ob-row-wrapper";
    wrapperTemplateBids.appendChild(bgTemplateBids);
    wrapperTemplateBids.appendChild(priceSpanTemplateBids);
    wrapperTemplateBids.appendChild(volSpanTemplate.cloneNode(true));

    for (let i = 0; i < numBids; i++) {
      const price = bids[i][0];
      const vol = bids[i][1];
      const pct = (vol / maxBidVol) * 100;

      const clone = wrapperTemplateBids.cloneNode(true);
      clone.children[0].style.width = pct + "%";
      clone.children[1].textContent = price.toFixed(1);
      clone.children[2].textContent = vol.toFixed(4);
      bidsFragment.appendChild(clone);
    }
    bidsContainer.textContent = "";
    bidsContainer.appendChild(bidsFragment);
  } catch (e) {
    console.error("renderOrderbook error:", e);
  }
}, 50);

// --- WebSocket Connection ---
const wsUrl = `ws://${window.location.host}/ws/stream`;
const ws = new WebSocket(wsUrl);

ws.onopen = () => {
  ws.send(JSON.stringify({ action: "auth", api_key: apiKey }));
  document.getElementById("connection-status").classList.add("display-none");
  document.getElementById("hud").classList.add("display-flex");
  addLog("[SYS] Neural Link Established", "#00ffcc");
  lastPing = Date.now();
};

ws.onmessage = (event) => {
  const payload = JSON.parse(event.data);
  const now = Date.now();
  const latency = now - lastPing;
  lastPing = now;

  // Update Latency and Timestamp
  const latencyEl = document.getElementById("val-latency");
  if (latencyEl) latencyEl.textContent = `${latency} ms`;

  // Format timestamp nicely
  const date = new Date();
  const timeStr = date.toISOString().replace("T", " ").substring(0, 19);
  const lastUpdatedEl = document.getElementById("val-last-updated");
  if (lastUpdatedEl) lastUpdatedEl.textContent = `UPDATED: ${timeStr}Z`;

  if (payload.type === "balance") {
    updateHUD(payload.data, "balance");
  } else if (payload.type === "synthesis") {
    updateHUD(payload.data, "synthesis");
  } else if (payload.type === "metric") {
    updateHUD(payload.data, "metric");
  } else if (payload.type === "tick") {
    // Feed tick to Candle Engine
    candleEngine.processTick(payload.data);
    globalVolume += payload.data.volume;
  } else if (payload.type === "signal") {
    updateHUD(payload, "signal");
    addLog(
      `> EXEC: ${payload.data.action} ${payload.data.asset_pair} | CONF: ${payload.data.confidence_score.toFixed(2)}`,
      "#ffaa00",
    );
    triggerTradeAlert(payload.data.action);
  } else if (payload.type === "orderbook") {
    const asksEl = document.getElementById("ob-asks");
    const bidsEl = document.getElementById("ob-bids");

    if (asksEl && bidsEl && payload.data.asks && payload.data.bids) {
      // Calculate max volume for depth bar scaling
      let maxVol = 0.001;
      const wsAsksCount = Math.min(payload.data.asks.length, 5);
      for (let i = 0; i < wsAsksCount; i++) {
        if (payload.data.asks[i][1] > maxVol) maxVol = payload.data.asks[i][1];
      }
      const wsBidsCount = Math.min(payload.data.bids.length, 5);
      for (let i = 0; i < wsBidsCount; i++) {
        if (payload.data.bids[i][1] > maxVol) maxVol = payload.data.bids[i][1];
      }

      // Render top 5 asks (reverse order so lowest is near spread)
      const topAsks = payload.data.asks.slice(0, 5).reverse();

      // PERFORMANCE OPTIMIZATION: Use DocumentFragment for batching DOM updates
      // 💡 What: Used DocumentFragment to batch DOM inserts instead of appending to DOM directly.
      // 🎯 Why: Reduces reflows/repaints, making the UI much more responsive during high-frequency orderbook updates.
      const rowTemplateAsk = document.createElement("div");
      rowTemplateAsk.className = "ob-row";
      rowTemplateAsk.appendChild(document.createElement("span"));
      rowTemplateAsk.appendChild(document.createElement("span"));
      const bgAsk = document.createElement("div");
      bgAsk.className = "ob-bg-ask";
      rowTemplateAsk.appendChild(bgAsk);

      const asksFragment = document.createDocumentFragment();
      topAsks.forEach((ask) => {
        const widthPct = Math.min(100, (ask[1] / maxVol) * 100);
        const clone = rowTemplateAsk.cloneNode(true);
        clone.children[0].textContent = ask[0].toFixed(2);
        clone.children[1].textContent = ask[1].toFixed(4);
        clone.children[2].style.width = widthPct + "%";
        asksFragment.appendChild(clone);
      });
      asksEl.textContent = "";
      asksEl.appendChild(asksFragment);

      // Render top 5 bids
      const topBids = payload.data.bids.slice(0, 5);

      const rowTemplateBid = document.createElement("div");
      rowTemplateBid.className = "ob-row";
      rowTemplateBid.appendChild(document.createElement("span"));
      rowTemplateBid.appendChild(document.createElement("span"));
      const bgBid = document.createElement("div");
      bgBid.className = "ob-bg-bid";
      rowTemplateBid.appendChild(bgBid);

      const bidsFragment = document.createDocumentFragment();
      topBids.forEach((bid) => {
        const widthPct = Math.min(100, (bid[1] / maxVol) * 100);
        const clone = rowTemplateBid.cloneNode(true);
        clone.children[0].textContent = bid[0].toFixed(2);
        clone.children[1].textContent = bid[1].toFixed(4);
        clone.children[2].style.width = widthPct + "%";
        bidsFragment.appendChild(clone);
      });
      bidsEl.textContent = "";
      bidsEl.appendChild(bidsFragment);
    }

    // Update L2 depth as well
    renderOrderbook(payload.data);
  } else if (payload.action === "kline") {
    if (candleSeries) {
      try {
        candleSeries.update(payload.data);
      } catch (e) {
        console.error("CandleSeries update error:", e);
      }
    } else {
      console.warn("Received kline but candleSeries is null");
    }
  }
};
function placeManualTrade(side) {
  if (ws.readyState !== WebSocket.OPEN) {
    addLog(`[ERR] WebSocket not connected`, "#ff0055");
    return;
  }

  try {
    const sizeEl = document.getElementById("trade-size");
    const symbolEl = document.getElementById("trade-symbol");

    if (!sizeEl || !symbolEl) {
      console.warn("Manual trade inputs not found");
      return;
    }

    const size = parseFloat(sizeEl.value);
    const symbol = symbolEl.value.toUpperCase() || "BTC/USDT";

    if (isNaN(size) || size <= 0) {
      addLog(`[ERR] Invalid order size`, "#ff0055");
      return;
    }

    addLog(
      `[MANUAL] Sending ${side.toUpperCase()} ${size} ${symbol}...`,
      "#00ffcc",
    );

    const payload = {
      action: "manual_trade",
      side: side,
      symbol: symbol,
      size: size,
    };
    ws.send(JSON.stringify(payload));
  } catch (e) {
    console.error("Place manual trade error:", e);
  }
}

function cancelAllTrades() {
  if (ws.readyState !== WebSocket.OPEN) {
    addLog(`[ERR] WebSocket not connected`, "#ff0055");
    return;
  }

  try {
    const symbolEl = document.getElementById("trade-symbol");
    const symbol = symbolEl
      ? symbolEl.value.toUpperCase() || "BTC/USDT"
      : "BTC/USDT";
    addLog(`[MANUAL] Sending CANCEL ALL for ${symbol}...`, "#ffaa00");

    const payload = {
      action: "cancel_all",
      symbol: symbol,
    };
    ws.send(JSON.stringify(payload));
  } catch (e) {
    console.error("Cancel all trades error:", e);
  }
}

try {
  document
    .getElementById("btn-buy")
    ?.addEventListener("click", () => placeManualTrade("buy"));
  document
    .getElementById("btn-sell")
    ?.addEventListener("click", () => placeManualTrade("sell"));
  document
    .getElementById("btn-cancel")
    ?.addEventListener("click", cancelAllTrades);
} catch (e) {
  console.error("Error setting up manual trade listeners:", e);
}

// --- 3D Interactive Crosshair ---
const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();

// Create crosshair mesh
const crosshairGeo = new THREE.RingGeometry(0.2, 0.3, 32);
const crosshairMat = new THREE.MeshBasicMaterial({
  color: 0x00ffcc,
  side: THREE.DoubleSide,
  transparent: true,
  opacity: 0.8,
});
const crosshair = new THREE.Mesh(crosshairGeo, crosshairMat);
crosshair.rotation.x = -Math.PI / 2;
scene.add(crosshair);

// Invisible plane to intersect with
const planeGeo = new THREE.PlaneGeometry(1000, 1000);
const planeMat = new THREE.MeshBasicMaterial({ visible: false });
const intersectPlane = new THREE.Mesh(planeGeo, planeMat);
intersectPlane.rotation.x = -Math.PI / 2;
scene.add(intersectPlane);

// Throttle mousemove
let isMouseMoving = false;
window.addEventListener("mousemove", (event) => {
  if (isMouseMoving) return;
  isMouseMoving = true;
  requestAnimationFrame(() => {
    // Calculate mouse position in normalized device coordinates
    mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

    // Raycast
    raycaster.setFromCamera(mouse, camera);
    const intersects = raycaster.intersectObject(intersectPlane);

    if (intersects.length > 0) {
      crosshair.position.copy(intersects[0].point);
      crosshair.position.y = 0.05; // slightly above floor
    }
    isMouseMoving = false;
  });
});

// --- Animation Loop ---
// --- Animation Loop ---
function animate() {
  // Use requestAnimationFrame at the top for smoother scheduling
  requestAnimationFrame(animate);

  // Resource Management: Pause rendering if tab is inactive
  if (document.hidden) return;

  currentGridColor.lerp(targetGridColor, 0.05);
  gridHelper.material.color = currentGridColor;
  pointLight.color = currentGridColor;

  // Also update particle color based on regime
  if (particleSystem && particleSystem.material) {
    particleSystem.material.color = currentGridColor;
  }

  // Particle animation
  if (particleSystem) {
    const positions = particleSystem.geometry.attributes.position.array;
    const speedMult = 1.0 + Math.min(globalVolume * 0.1, 5.0); // Speed scales with volume

    for (let i = 0; i < particleCount; i++) {
      positions[i * 3] += pVelocities[i * 3] * speedMult;
      positions[i * 3 + 1] += pVelocities[i * 3 + 1] * speedMult;
      positions[i * 3 + 2] += pVelocities[i * 3 + 2] * speedMult;

      // Boundary wrap
      if (positions[i * 3] > 20) positions[i * 3] = -20;
      if (positions[i * 3] < -20) positions[i * 3] = 20;
      if (positions[i * 3 + 1] > 10) positions[i * 3 + 1] = -10;
      if (positions[i * 3 + 1] < -10) positions[i * 3 + 1] = 10;
      if (positions[i * 3 + 2] > 20) positions[i * 3 + 2] = -20;
      if (positions[i * 3 + 2] < -20) positions[i * 3 + 2] = 20;
    }
    particleSystem.geometry.attributes.position.needsUpdate = true;
  }

  // Decay volume effect
  globalVolume *= 0.99;

  // Optional: Slow camera rotation or pan
  // scene.rotation.y += 0.0005;

  renderer.render(scene, camera);
}

// Throttle resize
let resizeTicking = false;
window.addEventListener("resize", () => {
  if (!resizeTicking) {
    requestAnimationFrame(() => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
      resizeTicking = false;
    });
    resizeTicking = true;
  }
});

animate();

let viewMode = "CITY"; // 'CITY' or 'HEATMAP'

document.getElementById("btn-toggle-view")?.addEventListener("click", () => {
  viewMode = viewMode === "CITY" ? "HEATMAP" : "CITY";
  document.getElementById("btn-toggle-view").textContent =
    `TOGGLE VIEW: ${viewMode}`;
  candleEngine.updateMeshes(); // Force redraw
});

// --- Admin & Settings API Hooks ---

const apiUrl = `http://${window.location.host}/api/v1`;

async function controlEngine(action) {
  try {
    const response = await fetch(`${apiUrl}/engine/control`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify({ action: action }),
    });
    const data = await response.json();
    if (data.status === "success") {
      addLog(`[SYS] ${data.message}`, "#ffaa00");
    }
  } catch (e) {
    addLog(`[ERR] API Control Error: ${e.message}`, "#ff0055");
  }
}

async function updatePortfolio(balance) {
  try {
    const response = await fetch(`${apiUrl}/portfolio`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify({ balance: parseFloat(balance) }),
    });
    const data = await response.json();
    if (data.status === "success") {
      addLog(`[SYS] ${data.message}`, "#00ffcc");
    }
  } catch (e) {
    addLog(`[ERR] API Portfolio Error: ${e.message}`, "#ff0055");
  }
}

async function setStrategy(strategyName) {
  try {
    const response = await fetch(`${apiUrl}/strategy`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify({ strategy: strategyName }),
    });
    const data = await response.json();
    if (data.status === "success") {
      addLog(`[SYS] ${data.message}`, "#00ffcc");
    }
  } catch (e) {
    addLog(`[ERR] API Strategy Error: ${e.message}`, "#ff0055");
  }
}

async function updateSettings(risk, dd) {
  try {
    const response = await fetch(`${apiUrl}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
      body: JSON.stringify({
        MAX_RISK_PER_TRADE_PCT: parseFloat(risk),
        DAILY_DRAWDOWN_LIMIT_PCT: parseFloat(dd),
      }),
    });
    const data = await response.json();
    if (data.status === "success") {
      addLog(`[SYS] Settings Updated`, "#00ffcc");
    }
  } catch (e) {
    addLog(`[ERR] API Settings Error: ${e.message}`, "#ff0055");
  }
}

// Event Listeners for Admin UI
document
  .getElementById("btn-pause")
  ?.addEventListener("click", () => controlEngine("pause"));
document
  .getElementById("btn-resume")
  ?.addEventListener("click", () => controlEngine("resume"));
document
  .getElementById("btn-kill")
  ?.addEventListener("click", () => controlEngine("kill_switch"));

document.getElementById("btn-set-balance")?.addEventListener("click", () => {
  try {
    const inputEl = document.getElementById("input-balance");
    if (inputEl) updatePortfolio(inputEl.value);
  } catch (e) {
    console.error("Set balance error:", e);
  }
});

document.getElementById("btn-set-strategy")?.addEventListener("click", () => {
  try {
    const selectEl = document.getElementById("select-strategy");
    if (selectEl) setStrategy(selectEl.value);
  } catch (e) {
    console.error("Set strategy error:", e);
  }
});

document
  .getElementById("btn-update-settings")
  ?.addEventListener("click", () => {
    try {
      const riskEl = document.getElementById("input-risk");
      const ddEl = document.getElementById("input-dd");
      if (riskEl && ddEl) updateSettings(riskEl.value, ddEl.value);
    } catch (e) {
      console.error("Update settings error:", e);
    }
  });

// --- VISUAL STRATEGY BUILDER (LiteGraph) ---
let graph = null;
let canvas = null;
let graphInitialized = false;

function initLiteGraph() {
  if (graphInitialized || !document.getElementById("strategy-canvas")) return;

  graph = new LGraph();
  canvas = new LGraphCanvas("#strategy-canvas", graph);

  // Custom Node: Price Input
  function PriceNode() {
    this.addOutput("Price", "number");
    this.title = "Market Price";
    this.color = "#333";
    this.bgcolor = "#111";
  }
  PriceNode.title = "Input / Market Price";
  LiteGraph.registerNodeType("input/price", PriceNode);

  // Custom Node: SMA
  function SmaNode() {
    this.addInput("Input", "number");
    this.addOutput("SMA", "number");
    this.addProperty("period", 14);
    this.widget = this.addWidget("number", "Period", 14, "period");
    this.title = "SMA";
    this.color = "#0055ff";
  }
  SmaNode.title = "Math / SMA";
  LiteGraph.registerNodeType("math/sma", SmaNode);

  // Custom Node: Compare
  function CompareNode() {
    this.addInput("A", "number");
    this.addInput("B", "number");
    this.addOutput("Trigger", "boolean");
    this.addProperty("op", ">");
    this.addWidget("combo", "Operator", ">", "op", {
      values: [">", "<", "==", ">=", "<="],
    });
    this.title = "Compare (Cross)";
    this.color = "#ffaa00";
  }
  CompareNode.title = "Logic / Compare";
  LiteGraph.registerNodeType("logic/compare", CompareNode);

  // Custom Node: Signal Output
  function SignalNode() {
    this.addInput("Trigger", "boolean");
    this.addProperty("signal_type", "buy");
    this.addWidget("combo", "Signal", "buy", "signal_type", {
      values: ["buy", "sell"],
    });
    this.title = "Strategy Output";
    this.color = "#00ffcc";
  }
  SignalNode.title = "Output / Signal";
  LiteGraph.registerNodeType("output/signal", SignalNode);

  // Add default nodes
  var node_price = LiteGraph.createNode("input/price");
  node_price.pos = [100, 200];
  graph.add(node_price);

  var node_sma = LiteGraph.createNode("math/sma");
  node_sma.pos = [300, 200];
  graph.add(node_sma);

  var node_comp = LiteGraph.createNode("logic/compare");
  node_comp.pos = [500, 200];
  graph.add(node_comp);

  var node_out = LiteGraph.createNode("output/signal");
  node_out.pos = [700, 200];
  graph.add(node_out);

  // Connect them
  node_price.connect(0, node_sma, 0);
  node_price.connect(0, node_comp, 0);
  node_sma.connect(0, node_comp, 1);
  node_comp.connect(0, node_out, 0);

  graph.start();
  graphInitialized = true;
}

document
  .getElementById("btn-save-strategy")
  ?.addEventListener("click", async () => {
    if (!graph) return;
    const data = graph.serialize();
    try {
      const res = await fetch("/api/v1/strategy/visual", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
        body: JSON.stringify(data),
      });
      const result = await res.json();
      if (result.status === "success") {
        addLog("Visual Strategy Saved Successfully", "SUCCESS");

        // Auto switch engine to use it
        await fetch("/api/v1/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
          body: JSON.stringify({ ACTIVE_STRATEGY: "VisualStrategy" }),
        });
        addLog("Engine swapped to VisualStrategy", "SUCCESS");
      } else {
        addLog("Failed to save Visual Strategy", "ERROR");
      }
    } catch (e) {
      addLog("Network error saving strategy", "ERROR");
    }
  });
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = "toast " + type;
  toast.textContent = message;

  container.appendChild(toast);

  // Automatically remove after animation completes (0.3s in + 4.5s wait + 0.5s out = 5.3s)
  setTimeout(() => {
    if (container.contains(toast)) {
      container.removeChild(toast);
    }
  }, 5500);
}
