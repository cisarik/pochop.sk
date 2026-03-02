(function () {
    const SIGNS = ['\u2648', '\u2649', '\u264A', '\u264B', '\u264C', '\u264D', '\u264E', '\u264F', '\u2650', '\u2651', '\u2652', '\u2653'];
    const SIGN_KEYS = ['aries', 'taurus', 'gemini', 'cancer', 'leo', 'virgo', 'libra', 'scorpio', 'sagittarius', 'capricorn', 'aquarius', 'pisces'];
    const SIGN_NAMES = ['Baran', 'Býk', 'Blíženci', 'Rak', 'Lev', 'Panna', 'Váhy', 'Škorpión', 'Strelec', 'Kozorožec', 'Vodnár', 'Ryby'];
    const SIGN_COLORS = ['#ff6b8f', '#ff9552', '#ffd166', '#7ed0ff', '#f7cd5d', '#92e58f', '#79f0ce', '#58b9ff', '#8d8aff', '#b699ff', '#c58bff', '#ff88d6'];
    function el(name, attrs) {
        const node = document.createElementNS('http://www.w3.org/2000/svg', name);
        Object.entries(attrs || {}).forEach(([k, v]) => node.setAttribute(k, v));
        return node;
    }

    function polarToXY(angle, radius, center) {
        const rad = (angle - 90) * Math.PI / 180;
        return {
            x: center + Math.cos(rad) * radius,
            y: center + Math.sin(rad) * radius,
        };
    }

    function bindTip({ node, text, tip, svg }) {
        if (!node || !tip || !svg) {
            return;
        }
        const moveTip = (e) => {
            const host = tip.offsetParent || svg.parentElement || svg;
            const box = host.getBoundingClientRect();
            const tipWidth = tip.offsetWidth || 64;
            const tipHeight = tip.offsetHeight || 26;
            const pad = 8;

            let x = e.clientX - box.left + 12;
            let y = e.clientY - box.top - 14;

            // Keep tooltip inside wheel container to avoid edge jumps.
            x = Math.max((tipWidth / 2) + pad, Math.min(box.width - (tipWidth / 2) - pad, x));
            y = Math.max(tipHeight + pad, Math.min(box.height - pad, y));

            tip.style.left = `${x}px`;
            tip.style.top = `${y}px`;
        };
        node.style.pointerEvents = 'all';
        node.addEventListener('mouseenter', (e) => {
            tip.textContent = text;
            tip.classList.add('is-visible');
            moveTip(e);
        });
        node.addEventListener('mousemove', moveTip);
        node.addEventListener('mouseleave', () => {
            tip.classList.remove('is-visible');
        });
    }

    function bindLexikonLink({ node, lexikonUrl, params }) {
        if (!node || !lexikonUrl) {
            return;
        }
        const openLexikon = () => {
            const url = new URL(lexikonUrl, window.location.origin);
            Object.entries(params || {}).forEach(([k, v]) => {
                if (v) url.searchParams.set(k, v);
            });
            window.location.href = url.toString();
        };
        node.style.cursor = 'pointer';
        node.setAttribute('role', 'link');
        node.setAttribute('tabindex', '0');
        node.addEventListener('click', (e) => {
            e.preventDefault();
            openLexikon();
        });
        node.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openLexikon();
            }
        });
    }

    function render(options) {
        const opts = options || {};
        const svg = document.getElementById(opts.svgId || 'momentWheel');
        if (!svg) {
            return;
        }

        const tip = opts.tipId ? document.getElementById(opts.tipId) : null;
        const lexikonUrl = opts.lexikonUrl || '';
        const planets = Array.isArray(opts.planets) ? opts.planets : [];
        const aspects = Array.isArray(opts.aspects) ? opts.aspects : [];

        const center = 310;
        const rOuter = 276;
        const rInner = 214;
        const rPlanet = 188;
        const maxAspects = Number.isFinite(opts.maxAspects) ? opts.maxAspects : 40;

        svg.innerHTML = '';

        const wheelBg = el('circle', { cx: center, cy: center, r: rOuter + 0.5, class: 'wheel-bg' });
        const ringOuter = el('circle', { cx: center, cy: center, r: rOuter, class: 'wheel-ring' });
        const ringInner = el('circle', { cx: center, cy: center, r: rInner, class: 'wheel-ring wheel-ring--inner' });
        svg.append(wheelBg, ringOuter, ringInner);

        for (let i = 0; i < 12; i += 1) {
            const angle = i * 30;
            const p1 = polarToXY(angle, rInner, center);
            const p2 = polarToXY(angle, rOuter, center);
            svg.appendChild(el('line', {
                x1: p1.x,
                y1: p1.y,
                x2: p2.x,
                y2: p2.y,
                class: 'wheel-divider',
            }));

            const mid = polarToXY(angle + 15, (rOuter + rInner) / 2, center);
            const signHalo = el('circle', {
                cx: mid.x,
                cy: mid.y,
                r: 16,
                class: 'wheel-sign-orb wheel-click-ready',
                fill: SIGN_COLORS[i],
                'data-sign-index': i,
                'data-sign-name': SIGN_NAMES[i],
            });
            svg.appendChild(signHalo);
            bindTip({ node: signHalo, text: SIGN_NAMES[i], tip, svg });
            bindLexikonLink({
                node: signHalo,
                lexikonUrl,
                params: {
                    sign: SIGN_KEYS[i],
                },
            });

            const signText = el('text', {
                x: mid.x,
                y: mid.y + 1,
                class: 'wheel-sign wheel-click-ready',
                fill: SIGN_COLORS[i],
                'data-sign-index': i,
                'data-sign-name': SIGN_NAMES[i],
            });
            signText.textContent = SIGNS[i];
            svg.appendChild(signText);
            bindTip({ node: signText, text: SIGN_NAMES[i], tip, svg });
            bindLexikonLink({
                node: signText,
                lexikonUrl,
                params: {
                    sign: SIGN_KEYS[i],
                },
            });
        }

        const planetByKey = {};
        planets.forEach((planet) => {
            planetByKey[planet.key] = planet;
        });

        aspects.slice(0, maxAspects).forEach((aspect, index) => {
            const p1 = planetByKey[aspect.planet1];
            const p2 = planetByKey[aspect.planet2];
            if (!p1 || !p2) {
                return;
            }
            const xy1 = polarToXY(p1.longitude, rPlanet, center);
            const xy2 = polarToXY(p2.longitude, rPlanet, center);
            const line = el('line', {
                x1: xy1.x,
                y1: xy1.y,
                x2: xy2.x,
                y2: xy2.y,
                class: `wheel-aspect wheel-aspect--${aspect.effect} wheel-click-ready`,
                'data-aspect-index': index,
                'data-planet1': aspect.planet1,
                'data-planet2': aspect.planet2,
                'data-aspect': aspect.aspect,
            });
            svg.appendChild(line);
            bindTip({
                node: line,
                text: `${aspect.planet1_name_sk} ${aspect.aspect_name_sk} ${aspect.planet2_name_sk}`,
                tip,
                svg,
            });
            bindLexikonLink({
                node: line,
                lexikonUrl,
                params: {
                    transit: `${aspect.planet1}-${aspect.aspect}-${aspect.planet2}`,
                },
            });
        });

        planets.forEach((planet) => {
            const xy = polarToXY(planet.longitude, rPlanet, center);

            const text = el('text', {
                x: xy.x,
                y: xy.y + 1,
                class: 'wheel-planet-symbol wheel-click-ready',
                'data-planet-key': planet.key,
                'data-planet-name': planet.name_sk,
            });
            text.textContent = planet.symbol;
            svg.appendChild(text);

            bindTip({ node: text, text: planet.name_sk, tip, svg });
            bindLexikonLink({
                node: text,
                lexikonUrl,
                params: {
                    planet: planet.key,
                },
            });
        });
    }

    window.PochopMomentWheel = {
        render,
    };
}());
