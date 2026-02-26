/**
 * Pochop — Cinematic Starfield v2
 * Realistic atmospheric scintillation, color shifts, flash events, cosmic dust
 */
(function () {
    'use strict';

    const canvas = document.getElementById('starfield');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    // ── Config ──
    const DPR = Math.min(window.devicePixelRatio || 1, 2);
    const DUST_COUNT = 350;          // faint background dust
    const STAR_COUNT = 280;          // normal twinkling stars
    const VIVID_COUNT = 40;          // strongly twinkling stars (scintillation)
    const BRIGHT_COUNT = 14;         // bright stars with glow + spikes
    const SHOOTING_INTERVAL = 7000;

    // ── Color palette — spectral classes ──
    const C = {
        O: [155, 176, 255],   // blue-hot
        B: [170, 191, 255],   // blue-white
        A: [202, 215, 255],   // white-blue
        F: [248, 247, 255],   // white
        G: [255, 244, 232],   // yellow-white
        K: [255, 218, 181],   // orange
        M: [255, 189, 150],   // red-orange
    };
    const SPECTRAL = [C.F, C.F, C.A, C.A, C.B, C.G, C.G, C.K, C.O, C.M];

    let W, H, stars, dust, vivid, bright, shootingStar, lastShot = 0, frameId;

    // ── Pseudo-noise (fast, deterministic per-star) ──
    function noise(seed, t) {
        // Multi-octave hash-noise for organic flicker
        const s1 = Math.sin(seed * 127.1 + t * 1.7) * 43758.5453;
        const s2 = Math.sin(seed * 269.5 + t * 3.1) * 18423.1237;
        const s3 = Math.sin(seed * 419.2 + t * 0.6) * 84741.7453;
        const n1 = s1 - Math.floor(s1);
        const n2 = s2 - Math.floor(s2);
        const n3 = s3 - Math.floor(s3);
        return n1 * 0.5 + n2 * 0.3 + n3 * 0.2;
    }

    // ── Resize ──
    function resize() {
        W = window.innerWidth;
        H = window.innerHeight;
        canvas.width = W * DPR;
        canvas.height = H * DPR;
        ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    }

    // ── Factory ──
    function mkDust() {
        return {
            x: Math.random() * W, y: Math.random() * H,
            r: 0.2 + Math.random() * 0.35,
            a: 0.08 + Math.random() * 0.18,
            color: SPECTRAL[Math.floor(Math.random() * SPECTRAL.length)],
        };
    }

    function mkStar(id) {
        const color = SPECTRAL[Math.floor(Math.random() * SPECTRAL.length)];
        return {
            id,
            x: Math.random() * W, y: Math.random() * H,
            r: 0.4 + Math.random() * 0.9,
            color,
            baseA: 0.35 + Math.random() * 0.55,
            // Twinkle params — 3 oscillators
            p1: Math.random() * 100, s1: 0.4 + Math.random() * 1.8,
            p2: Math.random() * 100, s2: 0.15 + Math.random() * 0.5,
            p3: Math.random() * 100, s3: 2.5 + Math.random() * 4.0,  // fast flicker
            d1: 0.2 + Math.random() * 0.35,  // depth
            d3: 0.05 + Math.random() * 0.1,  // fast-flicker depth
        };
    }

    function mkVivid(id) {
        // Stars with dramatic scintillation — like Sirius near the horizon
        const color = SPECTRAL[Math.floor(Math.random() * 4)]; // bluer
        return {
            id,
            x: Math.random() * W, y: Math.random() * H,
            r: 0.6 + Math.random() * 1.0,
            color,
            // Brighter base
            baseA: 0.5 + Math.random() * 0.5,
            // Scintillation — very fast irregular changes
            p1: Math.random() * 100, s1: 0.6 + Math.random() * 1.2,
            p2: Math.random() * 100, s2: 3.0 + Math.random() * 6.0,   // fast!
            p3: Math.random() * 100, s3: 7.0 + Math.random() * 12.0,  // very fast shimmer
            d1: 0.25 + Math.random() * 0.3,
            d2: 0.15 + Math.random() * 0.25,
            d3: 0.1 + Math.random() * 0.2,
            // Color shift range
            colorShift: 0.4 + Math.random() * 0.6,
            // Flash events — occasional bright spike
            flashSeed: Math.random() * 1000,
            flashInterval: 4 + Math.random() * 10,  // seconds between flashes
            flashDuration: 0.15 + Math.random() * 0.25,
        };
    }

    function mkBright(id) {
        const color = SPECTRAL[Math.floor(Math.random() * 5)];
        return {
            id,
            x: Math.random() * W, y: Math.random() * H,
            r: 1.4 + Math.random() * 1.0,
            color,
            baseA: 0.75 + Math.random() * 0.25,
            glowR: 10 + Math.random() * 20,
            spikeLen: 6 + Math.random() * 14,
            spikeA: 0.06 + Math.random() * 0.12,
            rot: Math.random() * Math.PI * 0.5,
            // Slow majestic pulse
            p1: Math.random() * 100, s1: 0.2 + Math.random() * 0.6,
            d1: 0.15 + Math.random() * 0.2,
            // Medium shimmer
            p2: Math.random() * 100, s2: 1.5 + Math.random() * 3.0,
            d2: 0.08 + Math.random() * 0.12,
            colorShift: 0.2 + Math.random() * 0.4,
        };
    }

    function init() {
        resize();
        dust = []; stars = []; vivid = []; bright = [];
        for (let i = 0; i < DUST_COUNT; i++) dust.push(mkDust());
        for (let i = 0; i < STAR_COUNT; i++) stars.push(mkStar(i));
        for (let i = 0; i < VIVID_COUNT; i++) vivid.push(mkVivid(i + 1000));
        for (let i = 0; i < BRIGHT_COUNT; i++) bright.push(mkBright(i + 2000));
    }

    // ── Drawing helpers ──
    function shiftColor(base, t, seed, amount) {
        // Subtle color temperature shift (atmospheric chromatic dispersion)
        const shift = Math.sin(t * 1.3 + seed) * amount;
        return [
            Math.min(255, Math.max(0, base[0] + shift * 30)),
            Math.min(255, Math.max(0, base[1] + shift * 10)),
            Math.min(255, Math.max(0, base[2] - shift * 25)),
        ];
    }

    function drawDust(d) {
        const [r, g, b] = d.color;
        ctx.beginPath();
        ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${r},${g},${b},${d.a})`;
        ctx.fill();
    }

    function drawRegularStar(s, t) {
        // 3-oscillator twinkle
        const tw1 = Math.sin(t * s.s1 + s.p1);
        const tw2 = Math.sin(t * s.s2 + s.p2);
        const tw3 = Math.sin(t * s.s3 + s.p3);
        const flicker = tw1 * s.d1 + tw2 * (1 - s.d1 - s.d3) * 0.3 + tw3 * s.d3;
        const a = s.baseA * Math.max(0.04, 1 - s.d1 + flicker);

        const [r, g, b] = s.color;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${r},${g},${b},${a})`;
        ctx.fill();

        // Soft glow on bigger ones
        if (s.r > 0.75 && a > 0.3) {
            ctx.beginPath();
            ctx.arc(s.x, s.y, s.r * 3.5, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${r},${g},${b},${a * 0.06})`;
            ctx.fill();
        }
    }

    function drawVividStar(s, t) {
        // Dramatic scintillation with noise
        const n = noise(s.id, t * 2.5);
        const tw1 = Math.sin(t * s.s1 + s.p1) * s.d1;
        const tw2 = Math.sin(t * s.s2 + s.p2) * s.d2;
        const tw3 = Math.sin(t * s.s3 + s.p3) * s.d3;
        let a = s.baseA * Math.max(0.03, 1 + tw1 + tw2 + tw3 - 0.3 + (n - 0.5) * 0.4);

        // Flash events — brief brightness spike
        const flashPhase = ((t + s.flashSeed) % s.flashInterval) / s.flashInterval;
        const flashWindow = s.flashDuration / s.flashInterval;
        if (flashPhase < flashWindow) {
            const flashIntensity = Math.sin((flashPhase / flashWindow) * Math.PI);
            a = Math.min(1.0, a + flashIntensity * 0.5);
        }

        a = Math.min(1.0, Math.max(0, a));

        // Color shift — atmospheric chromatic dispersion
        const col = shiftColor(s.color, t, s.id * 0.1, s.colorShift);
        const [r, g, b] = col;

        // Core
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${r},${g},${b},${a})`;
        ctx.fill();

        // Scintillation glow — size pulses with brightness
        if (a > 0.3) {
            const glowR = s.r * (2.5 + a * 3);
            const grad = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, glowR);
            grad.addColorStop(0, `rgba(${r},${g},${b},${a * 0.2})`);
            grad.addColorStop(0.5, `rgba(${r},${g},${b},${a * 0.05})`);
            grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
            ctx.beginPath();
            ctx.arc(s.x, s.y, glowR, 0, Math.PI * 2);
            ctx.fillStyle = grad;
            ctx.fill();
        }

        // Brief mini-spikes during flash
        if (flashPhase < flashWindow && a > 0.6) {
            ctx.save();
            ctx.translate(s.x, s.y);
            ctx.rotate(t * 0.3 + s.id);
            ctx.strokeStyle = `rgba(${r},${g},${b},${(a - 0.6) * 0.3})`;
            ctx.lineWidth = 0.4;
            const spk = s.r * 5 * a;
            for (let i = 0; i < 4; i++) {
                const ang = (i * Math.PI) / 2;
                ctx.beginPath();
                ctx.moveTo(0, 0);
                ctx.lineTo(Math.cos(ang) * spk, Math.sin(ang) * spk);
                ctx.stroke();
            }
            ctx.restore();
        }
    }

    function drawBrightStar(s, t) {
        const tw1 = Math.sin(t * s.s1 + s.p1) * s.d1;
        const tw2 = Math.sin(t * s.s2 + s.p2) * s.d2;
        const a = s.baseA * Math.max(0.3, 1 + tw1 + tw2);
        const col = shiftColor(s.color, t, s.id * 0.07, s.colorShift);
        const [r, g, b] = col;

        // Multi-layer glow
        const glowR = s.glowR * (0.85 + tw1 * 0.5);
        const g1 = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, glowR);
        g1.addColorStop(0, `rgba(${r},${g},${b},${a * 0.18})`);
        g1.addColorStop(0.25, `rgba(${r},${g},${b},${a * 0.08})`);
        g1.addColorStop(0.6, `rgba(${r},${g},${b},${a * 0.02})`);
        g1.addColorStop(1, `rgba(${r},${g},${b},0)`);
        ctx.beginPath();
        ctx.arc(s.x, s.y, glowR, 0, Math.PI * 2);
        ctx.fillStyle = g1;
        ctx.fill();

        // Diffraction spikes — 6-point (more realistic than 4)
        ctx.save();
        ctx.translate(s.x, s.y);
        ctx.rotate(s.rot);
        const len = s.spikeLen * (0.8 + tw1 * 0.4);
        for (let i = 0; i < 6; i++) {
            const ang = (i * Math.PI) / 3;
            // Tapered spike via gradient stroke
            const ex = Math.cos(ang) * len;
            const ey = Math.sin(ang) * len;
            const sg = ctx.createLinearGradient(0, 0, ex, ey);
            sg.addColorStop(0, `rgba(${r},${g},${b},${s.spikeA * a})`);
            sg.addColorStop(1, `rgba(${r},${g},${b},0)`);
            ctx.beginPath();
            ctx.moveTo(0, 0);
            ctx.lineTo(ex, ey);
            ctx.strokeStyle = sg;
            ctx.lineWidth = 0.6;
            ctx.stroke();
        }
        ctx.restore();

        // Bright core
        const cg = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, s.r * 2.5);
        cg.addColorStop(0, `rgba(255,255,255,${Math.min(1, a * 1.1)})`);
        cg.addColorStop(0.35, `rgba(${r},${g},${b},${a * 0.7})`);
        cg.addColorStop(1, `rgba(${r},${g},${b},0)`);
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r * 2.5, 0, Math.PI * 2);
        ctx.fillStyle = cg;
        ctx.fill();
    }

    // ── Shooting star ──
    function spawnShot() {
        return {
            x: Math.random() * W * 0.85,
            y: Math.random() * H * 0.35,
            angle: Math.PI * 0.12 + Math.random() * Math.PI * 0.22,
            speed: 350 + Math.random() * 450,
            len: 90 + Math.random() * 140,
            life: 0,
            maxLife: 0.7 + Math.random() * 0.5,
            a: 0.7 + Math.random() * 0.3,
            w: 1.0 + Math.random() * 1.2,
        };
    }

    function drawShot(ss, dt) {
        ss.life += dt;
        if (ss.life > ss.maxLife) return false;
        const p = ss.life / ss.maxLife;
        const a = ss.a * (p < 0.08 ? p / 0.08 : 1 - Math.pow((p - 0.08) / 0.92, 1.5));

        ss.x += Math.cos(ss.angle) * ss.speed * dt;
        ss.y += Math.sin(ss.angle) * ss.speed * dt;

        const tx = ss.x - Math.cos(ss.angle) * ss.len * (1 - p * 0.4);
        const ty = ss.y - Math.sin(ss.angle) * ss.len * (1 - p * 0.4);

        // Trail
        const tg = ctx.createLinearGradient(tx, ty, ss.x, ss.y);
        tg.addColorStop(0, `rgba(255,255,255,0)`);
        tg.addColorStop(0.5, `rgba(190,200,255,${a * 0.25})`);
        tg.addColorStop(1, `rgba(255,255,255,${a})`);
        ctx.beginPath();
        ctx.moveTo(tx, ty);
        ctx.lineTo(ss.x, ss.y);
        ctx.strokeStyle = tg;
        ctx.lineWidth = ss.w;
        ctx.lineCap = 'round';
        ctx.stroke();

        // Bright head
        const hg = ctx.createRadialGradient(ss.x, ss.y, 0, ss.x, ss.y, 5);
        hg.addColorStop(0, `rgba(255,255,255,${a})`);
        hg.addColorStop(0.5, `rgba(180,200,255,${a * 0.3})`);
        hg.addColorStop(1, 'rgba(180,200,255,0)');
        ctx.beginPath();
        ctx.arc(ss.x, ss.y, 5, 0, Math.PI * 2);
        ctx.fillStyle = hg;
        ctx.fill();

        return true;
    }

    // ── Render ──
    let last = 0;

    function render(ts) {
        const t = ts / 1000;
        const dt = last ? (ts - last) / 1000 : 0.016;
        last = ts;

        if (W !== window.innerWidth || H !== window.innerHeight) {
            resize();
            const redistribute = (arr) => arr.forEach(s => {
                if (s.x > W) s.x = Math.random() * W;
                if (s.y > H) s.y = Math.random() * H;
            });
            redistribute(dust); redistribute(stars);
            redistribute(vivid); redistribute(bright);
        }

        ctx.clearRect(0, 0, W, H);

        // Layer 1: cosmic dust (static, no twinkle)
        for (let i = 0; i < dust.length; i++) drawDust(dust[i]);

        // Layer 2: regular stars (gentle twinkle)
        for (let i = 0; i < stars.length; i++) drawRegularStar(stars[i], t);

        // Layer 3: vivid scintillating stars (dramatic)
        for (let i = 0; i < vivid.length; i++) drawVividStar(vivid[i], t);

        // Layer 4: bright stars (glow + spikes)
        for (let i = 0; i < bright.length; i++) drawBrightStar(bright[i], t);

        // Shooting stars
        if (ts - lastShot > SHOOTING_INTERVAL + Math.random() * 5000) {
            shootingStar = spawnShot();
            lastShot = ts;
        }
        if (shootingStar) {
            if (!drawShot(shootingStar, dt)) shootingStar = null;
        }

        frameId = requestAnimationFrame(render);
    }

    // ── Boot ──
    function boot() {
        init();
        frameId = requestAnimationFrame(render);
        window.addEventListener('resize', init);
    }

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            cancelAnimationFrame(frameId);
        } else {
            last = 0;
            frameId = requestAnimationFrame(render);
        }
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
