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
let pVelocities = [];
let globalVolume = 0;

// --- Initialize Particles ---
const pGeo = new THREE.BufferGeometry();
particleCount = 5000;
const pPos = new Float32Array(particleCount * 3);
pVelocities = [];

for (let i = 0; i < particleCount; i++) {
    pPos[i * 3] = (Math.random() - 0.5) * 40;
    pPos[i * 3 + 1] = (Math.random() - 0.5) * 20;
    pPos[i * 3 + 2] = (Math.random() - 0.5) * 40;
    pVelocities.push({
        x: (Math.random() - 0.5) * 0.05,
        y: (Math.random() - 0.5) * 0.05,
        z: (Math.random() - 0.5) * 0.05
    });
}
pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
const pMat = new THREE.PointsMaterial({
    color: 0x00ffcc,
    size: 0.1,
    transparent: true,
    opacity: 0.6,
    blending: THREE.AdditiveBlending
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
    candleSeries = chart.addCandleSeries( {
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
function updateHUD(data, type) {
  try {
    if (type === "synthesis") {
      const el = document.getElementById("val-synthesis");
      if (el) el.innerText = `[COPILOT] ${data.text}`;
    } else if (type === "balance") {
      const balEl = document.getElementById("val-balance");
      if (balEl && data.balance !== undefined) {
        balEl.innerText = `$${data.balance.toFixed(2)}`;
      }

      const modeEl = document.getElementById("val-mode");
      if (modeEl && data.mode) {
        modeEl.innerText = data.mode === "LIVE" ? "LIVE WARNING" : "DRY RUN";
        modeEl.className = `mode-indicator mode-${data.mode}`;
      }
    } else if (type === "signal") {
      const regimeClass = `regime-${data.regime}`;

      const regimeEl = document.getElementById("val-regime");
      if (regimeEl && data.regime) {
        regimeEl.innerText = data.regime;
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
                 addLog(`[CRITICAL] LIQUIDITY VELOCITY CIRCUIT BREAKER TRIPPED! (${vel.toFixed(2)})`, "#ff0055");
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

  overlay.className =
    action === "BUY" ? "flash-buy" : action === "SELL" ? "flash-sell" : "";
  if (overlay.className) {
    overlay.style.opacity = "1";
    overlay.style.transition = "none"; // Instant flash

    // Force reflow
    void overlay.offsetWidth;

    overlay.style.transition = "opacity 1s ease-out";
    overlay.style.opacity = "0";
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
    entry.innerText = text;
    logPanel.appendChild(entry);

    if (logPanel.children.length > 8) {
      logPanel.removeChild(logPanel.firstChild);
    }
  } catch (e) {
    console.error("addLog error:", e);
  }
}

// --- Handle Orderbook Depth Visuals ---
function renderOrderbook(data) {
  try {
    const asksContainer = document.getElementById("depth-asks");
    const bidsContainer = document.getElementById("depth-bids");
    if (!asksContainer || !bidsContainer) return;

    const asks = data.asks || [];
    const bids = data.bids || [];

    // Render top 5
    let asksHtml = "";
    let maxAskVol = Math.max(...asks.slice(0, 5).map((a) => a[1]), 0.001);
    for (let i = Math.min(asks.length - 1, 4); i >= 0; i--) {
      const price = asks[i][0];
      const vol = asks[i][1];
      const pct = (vol / maxAskVol) * 100;
      asksHtml += `
            <div style="position: relative; height: 16px; font-size: 0.75rem; display: flex; justify-content: space-between; align-items: center;">
                <div style="position: absolute; right: 0; top: 0; height: 100%; width: ${pct}%; background: rgba(255, 0, 85, 0.3); z-index: 0;"></div>
                <span style="color: #ff0055; z-index: 1;">${price.toFixed(1)}</span>
                <span style="z-index: 1; opacity: 0.8;">${vol.toFixed(4)}</span>
            </div>
        `;
    }
    asksContainer.innerHTML = asksHtml;

    let bidsHtml = "";
    let maxBidVol = Math.max(...bids.slice(0, 5).map((b) => b[1]), 0.001);
    for (let i = 0; i < Math.min(bids.length, 5); i++) {
      const price = bids[i][0];
      const vol = bids[i][1];
      const pct = (vol / maxBidVol) * 100;
      bidsHtml += `
            <div style="position: relative; height: 16px; font-size: 0.75rem; display: flex; justify-content: space-between; align-items: center;">
                <div style="position: absolute; left: 0; top: 0; height: 100%; width: ${pct}%; background: rgba(0, 255, 204, 0.3); z-index: 0;"></div>
                <span style="color: #00ffcc; z-index: 1;">${price.toFixed(1)}</span>
                <span style="z-index: 1; opacity: 0.8;">${vol.toFixed(4)}</span>
            </div>
        `;
    }
    bidsContainer.innerHTML = bidsHtml;
  } catch (e) {
    console.error("renderOrderbook error:", e);
  }
}

// --- WebSocket Connection ---
const wsUrl = `ws://${window.location.host}/ws/stream`;
const ws = new WebSocket(wsUrl);

ws.onopen = () => {
  document.getElementById("connection-status").style.display = "none";
  document.getElementById("hud").style.display = "flex";
  addLog("[SYS] Neural Link Established", "#00ffcc");
  lastPing = Date.now();
};

ws.onmessage = (event) => {
  const payload = JSON.parse(event.data);

  // Update Latency and Timestamp
  const now = Date.now();
  document.getElementById("val-latency").innerText = `${now - lastPing} ms`;
  lastPing = now;

  // Format timestamp nicely
  const date = new Date();
  const timeStr = date.toISOString().replace("T", " ").substring(0, 19);
  document.getElementById("val-last-updated").innerText =
    `UPDATED: ${timeStr}Z`;

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
      const maxVol = Math.max(
        ...payload.data.asks.slice(0, 5).map((a) => a[1]),
        ...payload.data.bids.slice(0, 5).map((b) => b[1]),
      );

      // Render top 5 asks (reverse order so lowest is near spread)
      let asksHtml = "";
      const topAsks = payload.data.asks.slice(0, 5).reverse();
      topAsks.forEach((ask) => {
        const widthPct = Math.min(100, (ask[1] / maxVol) * 100);
        asksHtml += `<div class="ob-row">
                                <span>${ask[0].toFixed(2)}</span>
                                <span>${ask[1].toFixed(4)}</span>
                                <div class="ob-bg-ask" style="width: ${widthPct}%"></div>
                             </div>`;
      });
      asksEl.innerHTML = asksHtml;

      // Render top 5 bids
      let bidsHtml = "";
      const topBids = payload.data.bids.slice(0, 5);
      topBids.forEach((bid) => {
        const widthPct = Math.min(100, (bid[1] / maxVol) * 100);
        bidsHtml += `<div class="ob-row">
                                <span>${bid[0].toFixed(2)}</span>
                                <span>${bid[1].toFixed(4)}</span>
                                <div class="ob-bg-bid" style="width: ${widthPct}%"></div>
                             </div>`;
      });
      bidsEl.innerHTML = bidsHtml;
    }
  } else if (payload.action === "kline") {
    if (candleSeries) {
      try {
        candleSeries.update(payload.data);
      } catch (e) {
        console.error("CandleSeries update error:", e);
      }
    } else {
      console.warn("candleSeries not initialized, cannot update kline");
    }
  }
};

ws.onerror = (error) => {
  console.error("WebSocket Error:", error);
  document.getElementById("connection-status").innerText = "LINK SEVERED";
  document.getElementById("connection-status").style.color = "#ff0055";
  document.getElementById("connection-status").style.display = "block";
};

// --- Manual Trading Hooks ---
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
function animate() {
  // Resource Management: Pause rendering if tab is inactive
  if (!document.hidden) {
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
        positions[i * 3] += pVelocities[i].x * speedMult;
        positions[i * 3 + 1] += pVelocities[i].y * speedMult;
        positions[i * 3 + 2] += pVelocities[i].z * speedMult;

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

  requestAnimationFrame(animate);
}

// Debounce resize
let resizeTimeout;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimeout);
  resizeTimeout = setTimeout(() => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  }, 100);
});

animate();

let viewMode = "CITY"; // 'CITY' or 'HEATMAP'

document.getElementById("btn-toggle-view")?.addEventListener("click", () => {
  viewMode = viewMode === "CITY" ? "HEATMAP" : "CITY";
  document.getElementById("btn-toggle-view").innerText =
    `TOGGLE VIEW: ${viewMode}`;
  candleEngine.updateMeshes(); // Force redraw
});

// --- Admin & Settings API Hooks ---

const apiUrl = `http://${window.location.hostname}:8000/api/v1`;

async function controlEngine(action) {
  try {
    const response = await fetch(`${apiUrl}/engine/control`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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
      headers: { "Content-Type": "application/json" },
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
      headers: { "Content-Type": "application/json" },
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
      headers: { "Content-Type": "application/json" },
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