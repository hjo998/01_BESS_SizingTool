/**
 * charts.js — SI Sizing Tool Ver.2.0
 * Canvas-based Dischargeable Energy @POI chart. No external dependencies.
 * Offline-first: pure Canvas API implementation.
 */

var BESSCharts = (function () {
    'use strict';

    // ── Palette ────────────────────────────────────────────────
    var COLORS = {
        grid:       '#E8E8E8',
        axis:       '#555555',
        label:      '#555555',
        baseLine:   '#888888',
        augLine:    '#A50034',
        required:   '#0069D9',
        augment:    '#E65C00',
        fillBase:   'rgba(136,136,136,0.06)',
        fillAug:    'rgba(165,0,52,0.08)',
        dotFill:    '#FFFFFF',
        title:      '#1A1A1A',
    };

    var FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";

    // ── Helpers ────────────────────────────────────────────────
    function resolveCanvas(idOrElem) {
        if (typeof idOrElem === 'string') {
            return document.getElementById(idOrElem);
        }
        return idOrElem;
    }

    function lerp(a, b, t) { return a + (b - a) * t; }

    function mapVal(val, dMin, dMax, pMin, pMax) {
        if (dMax === dMin) return (pMin + pMax) / 2;
        var t = (val - dMin) / (dMax - dMin);
        return lerp(pMin, pMax, t);
    }

    // ── Main Draw Function ─────────────────────────────────────
    /**
     * Draw Dischargeable Energy @POI chart onto a <canvas> element.
     *
     * @param {string|HTMLCanvasElement} canvasId
     * @param {object}  retentionData       Full retention response from API
     * @param {number}  requiredEnergyPoi   Required energy @POI (MWh) — horizontal line
     * @param {Array<{year:number, label:string}>} augMarkers
     */
    function drawRetentionCurve(canvasId, retentionData, requiredEnergyPoi, augMarkers) {
        var canvas = resolveCanvas(canvasId);
        if (!canvas) return;

        // Accept both old format (array of [year, pct]) and new format (full retention object)
        var curveData, retentionByYear, baseRetentionByYear, hasAug;

        if (Array.isArray(retentionData)) {
            // Legacy: curveData = [[year, pct], ...]
            curveData = retentionData;
            retentionByYear = null;
            baseRetentionByYear = null;
            hasAug = false;
        } else {
            // New format: full retention response
            curveData = retentionData.curve || [];
            retentionByYear = retentionData.retention_by_year || null;
            baseRetentionByYear = retentionData.base_retention_by_year || null;
            hasAug = retentionData.lookup_source && retentionData.lookup_source.indexOf('augmentation') !== -1;
        }

        if (!curveData || curveData.length === 0) return;

        // Responsive: match CSS width
        var cssWidth = canvas.parentElement ? canvas.parentElement.clientWidth - 32 : 800;
        canvas.width  = Math.max(cssWidth, 400);
        canvas.height = parseInt(canvas.getAttribute('height') || '320', 10);

        var ctx = canvas.getContext('2d');
        var W = canvas.width;
        var H = canvas.height;

        // Margins
        var margin = { top: 28, right: 40, bottom: 56, left: 72 };
        var plotW = W - margin.left - margin.right;
        var plotH = H - margin.top  - margin.bottom;

        // Build energy data series
        var years = curveData.map(function (d) { return d[0]; });
        var xMin = Math.min.apply(null, years);
        var xMax = Math.max.apply(null, years);

        // Primary series: Dischargeable Energy @POI (augmented if applicable)
        var augPoiSeries = [];
        // Base series: without augmentation
        var basePoiSeries = [];

        if (retentionByYear) {
            years.forEach(function (yr) {
                var d = retentionByYear[String(yr)];
                if (d) {
                    augPoiSeries.push({ year: yr, energy: d.dischargeable_energy_poi_mwh });
                }
            });
        }

        if (baseRetentionByYear && hasAug) {
            years.forEach(function (yr) {
                var d = baseRetentionByYear[String(yr)];
                if (d) {
                    basePoiSeries.push({ year: yr, energy: d.dischargeable_energy_poi_mwh });
                }
            });
        }

        // If no detailed data, fall back to old retention % display
        var useEnergyMode = augPoiSeries.length > 0;
        var primarySeries = useEnergyMode ? augPoiSeries : curveData.map(function (d) { return { year: d[0], energy: d[1] }; });

        // Y-axis range
        var allEnergies = primarySeries.map(function (d) { return d.energy; });
        if (basePoiSeries.length) {
            basePoiSeries.forEach(function (d) { allEnergies.push(d.energy); });
        }
        if (useEnergyMode && requiredEnergyPoi > 0) {
            allEnergies.push(requiredEnergyPoi);
        }

        var yDataMin = Math.min.apply(null, allEnergies);
        var yDataMax = Math.max.apply(null, allEnergies);

        // Add 10% padding
        var yRange = yDataMax - yDataMin || 1;
        var yMin, yMax;
        if (useEnergyMode) {
            yMin = Math.max(0, Math.floor((yDataMin - yRange * 0.1) * 10) / 10);
            yMax = Math.ceil((yDataMax + yRange * 0.1) * 10) / 10;
        } else {
            yMin = 60;
            yMax = 105;
        }

        function px(year) { return margin.left + mapVal(year, xMin, xMax, 0, plotW); }
        function py(val)  { return margin.top  + mapVal(val,  yMax, yMin, 0, plotH); }

        // ── Clear ──
        ctx.clearRect(0, 0, W, H);

        // ── Background ──
        ctx.fillStyle = '#FAFAFA';
        ctx.fillRect(0, 0, W, H);

        // ── Grid lines ──
        ctx.strokeStyle = COLORS.grid;
        ctx.lineWidth = 1;

        // Y-axis ticks
        var yTickCount = 8;
        var yStep = (yMax - yMin) / yTickCount;
        // Round step to nice number
        if (useEnergyMode) {
            var magnitude = Math.pow(10, Math.floor(Math.log10(yStep)));
            yStep = Math.ceil(yStep / magnitude) * magnitude;
        } else {
            yStep = 5;
        }

        for (var yTick = Math.ceil(yMin / yStep) * yStep; yTick <= yMax; yTick += yStep) {
            var y = py(yTick);
            ctx.beginPath();
            ctx.moveTo(margin.left, y);
            ctx.lineTo(margin.left + plotW, y);
            ctx.stroke();

            ctx.fillStyle = COLORS.label;
            ctx.font = '11px ' + FONT;
            ctx.textAlign = 'right';
            ctx.textBaseline = 'middle';
            if (useEnergyMode) {
                ctx.fillText(yTick.toFixed(1), margin.left - 8, y);
            } else {
                ctx.fillText(yTick + '%', margin.left - 8, y);
            }
        }

        // X-axis ticks
        var xStep = xMax <= 10 ? 1 : 2;
        for (var yr = xMin; yr <= xMax; yr += xStep) {
            var x = px(yr);
            ctx.beginPath();
            ctx.moveTo(x, margin.top);
            ctx.lineTo(x, margin.top + plotH);
            ctx.stroke();

            ctx.fillStyle = COLORS.label;
            ctx.font = '11px ' + FONT;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            ctx.fillText(yr, x, margin.top + plotH + 8);
        }

        // ── Axes ──
        ctx.strokeStyle = COLORS.axis;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(margin.left, margin.top);
        ctx.lineTo(margin.left, margin.top + plotH);
        ctx.lineTo(margin.left + plotW, margin.top + plotH);
        ctx.stroke();

        // ── Required Energy Line ──
        if (useEnergyMode && requiredEnergyPoi > 0 && requiredEnergyPoi >= yMin && requiredEnergyPoi <= yMax) {
            var yReq = py(requiredEnergyPoi);
            ctx.save();
            ctx.strokeStyle = COLORS.required;
            ctx.lineWidth = 1.5;
            ctx.setLineDash([6, 4]);
            ctx.beginPath();
            ctx.moveTo(margin.left, yReq);
            ctx.lineTo(margin.left + plotW, yReq);
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.restore();

            ctx.fillStyle = COLORS.required;
            ctx.font = 'bold 10px ' + FONT;
            ctx.textAlign = 'left';
            ctx.textBaseline = 'bottom';
            ctx.fillText('Required Energy @POI (' + requiredEnergyPoi.toFixed(1) + ' MWh)', margin.left + 4, yReq - 3);
        } else if (!useEnergyMode) {
            // Legacy: EOL threshold line at 60%
            var yEol = py(60);
            ctx.save();
            ctx.strokeStyle = COLORS.required;
            ctx.lineWidth = 1.5;
            ctx.setLineDash([6, 4]);
            ctx.beginPath();
            ctx.moveTo(margin.left, yEol);
            ctx.lineTo(margin.left + plotW, yEol);
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.restore();
            ctx.fillStyle = COLORS.required;
            ctx.font = 'bold 10px ' + FONT;
            ctx.textAlign = 'left';
            ctx.textBaseline = 'bottom';
            ctx.fillText('EOL Threshold (60%)', margin.left + 4, yEol - 3);
        }

        // ── Augmentation Markers ──
        if (augMarkers && augMarkers.length) {
            augMarkers.forEach(function (m) {
                var mx = px(m.year);
                ctx.save();
                ctx.strokeStyle = COLORS.augment;
                ctx.lineWidth = 1.5;
                ctx.setLineDash([4, 3]);
                ctx.beginPath();
                ctx.moveTo(mx, margin.top);
                ctx.lineTo(mx, margin.top + plotH);
                ctx.stroke();
                ctx.setLineDash([]);

                // Triangle marker
                ctx.fillStyle = COLORS.augment;
                ctx.beginPath();
                ctx.moveTo(mx, margin.top + 6);
                ctx.lineTo(mx - 5, margin.top - 2);
                ctx.lineTo(mx + 5, margin.top - 2);
                ctx.closePath();
                ctx.fill();

                ctx.font = 'bold 9px ' + FONT;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'bottom';
                ctx.fillText('AUG Yr' + m.year, mx, margin.top - 4);
                ctx.restore();
            });
        }

        // ── Base Decay Fill + Line (when augmentation is active) ──
        if (basePoiSeries.length > 1) {
            // Fill
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(px(basePoiSeries[0].year), py(basePoiSeries[0].energy));
            for (var bi = 1; bi < basePoiSeries.length; bi++) {
                ctx.lineTo(px(basePoiSeries[bi].year), py(basePoiSeries[bi].energy));
            }
            ctx.lineTo(px(basePoiSeries[basePoiSeries.length - 1].year), margin.top + plotH);
            ctx.lineTo(px(basePoiSeries[0].year), margin.top + plotH);
            ctx.closePath();
            ctx.fillStyle = COLORS.fillBase;
            ctx.fill();
            ctx.restore();

            // Line
            ctx.save();
            ctx.strokeStyle = COLORS.baseLine;
            ctx.lineWidth = 1.5;
            ctx.setLineDash([5, 3]);
            ctx.lineJoin = 'round';
            ctx.beginPath();
            ctx.moveTo(px(basePoiSeries[0].year), py(basePoiSeries[0].energy));
            for (var bj = 1; bj < basePoiSeries.length; bj++) {
                ctx.lineTo(px(basePoiSeries[bj].year), py(basePoiSeries[bj].energy));
            }
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.restore();
        }

        // ── Primary Line Fill ──
        if (primarySeries.length > 1) {
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(px(primarySeries[0].year), py(primarySeries[0].energy));
            for (var fi = 1; fi < primarySeries.length; fi++) {
                ctx.lineTo(px(primarySeries[fi].year), py(primarySeries[fi].energy));
            }
            ctx.lineTo(px(primarySeries[primarySeries.length - 1].year), margin.top + plotH);
            ctx.lineTo(px(primarySeries[0].year), margin.top + plotH);
            ctx.closePath();
            ctx.fillStyle = COLORS.fillAug;
            ctx.fill();
            ctx.restore();
        }

        // ── Primary Line ──
        if (primarySeries.length > 1) {
            ctx.save();
            ctx.strokeStyle = hasAug ? COLORS.augLine : COLORS.augLine;
            ctx.lineWidth = 2.5;
            ctx.lineJoin = 'round';
            ctx.beginPath();
            ctx.moveTo(px(primarySeries[0].year), py(primarySeries[0].energy));
            for (var pj = 1; pj < primarySeries.length; pj++) {
                ctx.lineTo(px(primarySeries[pj].year), py(primarySeries[pj].energy));
            }
            ctx.stroke();
            ctx.restore();
        }

        // ── Data Points ──
        primarySeries.forEach(function (d) {
            var cx = px(d.year);
            var cy = py(d.energy);
            ctx.beginPath();
            ctx.arc(cx, cy, 3.5, 0, 2 * Math.PI);
            ctx.fillStyle = COLORS.dotFill;
            ctx.strokeStyle = COLORS.augLine;
            ctx.lineWidth = 2;
            ctx.fill();
            ctx.stroke();
        });

        // ── Axis Labels ──
        ctx.fillStyle = COLORS.title;
        ctx.font = 'bold 12px ' + FONT;

        // Y axis label
        ctx.save();
        ctx.translate(14, margin.top + plotH / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(useEnergyMode ? 'Dischargeable Energy @POI (MWh)' : 'Retention (%)', 0, 0);
        ctx.restore();

        // X axis label
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText('Year', margin.left + plotW / 2, margin.top + plotH + 32);

        // ── Legend ──
        var legendX = margin.left + plotW - 220;
        var legendY = margin.top + 8;
        var legendItems = [];

        if (hasAug && basePoiSeries.length) {
            legendItems.push({ color: COLORS.baseLine, dash: true,  label: 'Base Decay (no aug.)' });
            legendItems.push({ color: COLORS.augLine,  dash: false, label: 'With Augmentation' });
        } else {
            legendItems.push({ color: COLORS.augLine, dash: false, label: useEnergyMode ? 'Dischargeable @POI' : 'Capacity Retention' });
        }

        if (useEnergyMode && requiredEnergyPoi > 0) {
            legendItems.push({ color: COLORS.required, dash: true, label: 'Required Energy @POI' });
        } else if (!useEnergyMode) {
            legendItems.push({ color: COLORS.required, dash: true, label: 'EOL Threshold (60%)' });
        }

        if (augMarkers && augMarkers.length) {
            legendItems.push({ color: COLORS.augment, dash: true, label: 'Augmentation' });
        }

        legendItems.forEach(function (item, idx) {
            var lx = legendX;
            var ly = legendY + idx * 18;

            ctx.save();
            ctx.strokeStyle = item.color;
            ctx.lineWidth = 2;
            if (item.dash) ctx.setLineDash([5, 3]);
            ctx.beginPath();
            ctx.moveTo(lx, ly + 7);
            ctx.lineTo(lx + 24, ly + 7);
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.restore();

            ctx.fillStyle = COLORS.label;
            ctx.font = '11px ' + FONT;
            ctx.textAlign = 'left';
            ctx.textBaseline = 'middle';
            ctx.fillText(item.label, lx + 30, ly + 7);
        });

        // ── Border ──
        ctx.strokeStyle = '#D0D0D0';
        ctx.lineWidth = 1;
        ctx.strokeRect(0.5, 0.5, W - 1, H - 1);
    }

    // ── Public API ─────────────────────────────────────────────
    return {
        drawRetentionCurve: drawRetentionCurve,
    };
}());
