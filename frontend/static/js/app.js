/**
 * app.js — SI Sizing Tool Ver.2.0
 * Tab switching, form submission, live efficiency preview,
 * product dropdown population, project save/load.
 * Offline-first: no external dependencies.
 */

(function () {
    'use strict';

    // ── State ──────────────────────────────────────────────────
    var lastResult = null;
    // augWaveCount removed — now tracked via DOM chip count
    var MAX_AUG_WAVES = 4;
    var auxStageCount = 0;
    var MAX_AUX_STAGES = 5;

    // ── Case/Project context (set from URL params) ─────────────
    var _caseId    = null;   // integer or null
    var _projectId = null;   // integer or null

    // ── DOM Ready ──────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', function () {
        initTabs();
        initEfficiencyPreview();
        loadProductOptions();
        initCaseContext();
        initPoiVoltageLevel();
        initRestSocSync();
        initDefinitionTooltips();
        initUsagePattern();
    });

    // ── POI Level → Voltage Level toggle ──
    function initPoiVoltageLevel() {
        var poiSel = document.getElementById('poiLevel');
        var vlGroup = document.getElementById('voltageLevelGroup');
        if (!poiSel || !vlGroup) return;
        function toggle() {
            vlGroup.style.display = poiSel.value ? 'block' : 'none';
        }
        poiSel.addEventListener('change', toggle);
        toggle();
    }

    // ── Rest SOC Type ↔ Value sync ──
    function initRestSocSync() {
        var typeSel = document.getElementById('restSocType');
        var valInp  = document.getElementById('restSocValue');
        if (!typeSel || !valInp) return;
        var presets = { High: 40, Mid: 30, Low: 20 };
        typeSel.addEventListener('change', function () {
            if (presets[typeSel.value] !== undefined) {
                valInp.value = presets[typeSel.value];
            }
        });
    }

    // ══════════════════════════════════════════════════════════
    // CASE / PROJECT CONTEXT  (URL params: ?case_id=X&project_id=Y)
    // ══════════════════════════════════════════════════════════
    function initCaseContext() {
        var params = new URLSearchParams(window.location.search);
        var caseIdStr    = params.get('case_id');
        var projectIdStr = params.get('project_id');

        if (!caseIdStr) return;   // standalone mode — no-op

        _caseId    = parseInt(caseIdStr, 10);
        _projectId = projectIdStr ? parseInt(projectIdStr, 10) : null;

        if (isNaN(_caseId)) { _caseId = null; return; }

        showCaseBanner('Loading case\u2026', 'loading');

        fetch('/api/cases/' + _caseId)
            .then(function (r) {
                if (!r.ok) throw new Error('Case not found (HTTP ' + r.status + ')');
                return r.json();
            })
            .then(function (caseData) {
                var inputData = caseData.input_data || {};

                // Wait for product dropdowns to settle before populating
                waitForDropdowns(function () {
                    populateFormFromData(inputData);
                });

                showCaseBanner(
                    'Editing Case: <strong>' + escCaseHtml(caseData.case_name || '') + '</strong>' +
                    (_projectId
                        ? ' &nbsp;|&nbsp; <a href="/project/' + _projectId + '/cases">Back to Cases</a>'
                        : ''),
                    'active'
                );

                // Show bottom action buttons for case context
                var btnSaveBottom = document.getElementById('btnSaveToCaseBottom');
                var btnBackBottom = document.getElementById('btnBackToCasesBottom');
                if (btnSaveBottom) btnSaveBottom.style.display = '';
                if (btnBackBottom && _projectId) {
                    btnBackBottom.style.display = '';
                    btnBackBottom.href = '/project/' + _projectId + '/cases';
                }
            })
            .catch(function (err) {
                showCaseBanner('Could not load case: ' + err.message, 'error');
                _caseId = null;
            });
    }

    /**
     * Poll every 80 ms (max 3 s) until the battery product dropdown is populated,
     * then call callback.
     */
    function waitForDropdowns(callback) {
        var attempts = 0;
        var maxAttempts = 38;
        var timer = setInterval(function () {
            var batSel = document.getElementById('batteryProductType');
            attempts++;
            if ((batSel && batSel.options.length > 1) || attempts >= maxAttempts) {
                clearInterval(timer);
                callback();
            }
        }, 80);
    }

    /**
     * Populate every form field from a saved input_data object.
     * Mirrors the field-id mapping in collectFormData().
     */
    function populateFormFromData(d) {
        function setVal(id, v) {
            if (v === undefined || v === null) return;
            var el = document.getElementById(id);
            if (!el) return;
            el.value = v;
            el.dispatchEvent(new Event('change'));
        }

        // Tab 1 — Project Basic
        setVal('projectTitle',       d.project_title);
        setVal('customer',           d.customer);
        setVal('projectLife',        d.project_life);
        setVal('application',        d.application);
        setVal('measurementMethod',  d.measurement_method);
        setVal('requiredPower',      d.required_power_mw);
        setVal('requiredEnergy',     d.required_energy_mwh);
        setVal('poiLevel',           d.poi_level);
        setVal('voltageLevel',       d.voltage_level_kv);
        setVal('powerFactor',        d.power_factor);
        setVal('auxPowerSource',     d.aux_power_source);
        setVal('temperature',        d.temperature_c);
        setVal('altitude',           d.altitude);

        // Tab 2 — Efficiency
        setVal('hvAcCabling',        d.hv_ac_cabling);
        setVal('hvTransformer',      d.hv_transformer);
        setVal('mvAcCabling',        d.mv_ac_cabling);
        setVal('mvTransformer',      d.mv_transformer);
        setVal('lvCabling',          d.lv_cabling);
        setVal('pcsEfficiency',      d.pcs_efficiency);
        setVal('dcCabling',          d.dc_cabling);
        setVal('branchingPoint',     d.branching_point);
        setVal('auxTrLv',            d.aux_tr_lv);
        setVal('auxLineLv',          d.aux_line_lv);
        setVal('appliedDod',         d.applied_dod);
        setVal('lossFactors',        d.loss_factors);
        setVal('mbmsConsumption',    d.mbms_consumption);

        // Power Flow equipment parameters
        setVal('pfPcsVoltage',  d.pf_pcs_voltage_kv);
        setVal('pfLvR',         d.pf_lv_r_ohm_per_km);
        setVal('pfLvX',         d.pf_lv_x_ohm_per_km);
        if (d.pf_lv_length_km != null) setVal('pfLvLen', d.pf_lv_length_km * 1000);  // km → m for UI
        setVal('pfMvtCapacity', d.pf_mvt_capacity_mva);
        setVal('pfMvtEff',      d.pf_mvt_efficiency_pct);
        setVal('pfMvtZ',        d.pf_mvt_impedance_pct);
        setVal('pfMvR',         d.pf_mv_r_ohm_per_km);
        setVal('pfMvX',         d.pf_mv_x_ohm_per_km);
        setVal('pfMvLen',       d.pf_mv_length_km);
        setVal('pfMvVoltage',   d.pf_mv_voltage_kv);
        setVal('pfMptCapacity', d.pf_mpt_capacity_mva);
        setVal('pfMptEff',      d.pf_mpt_efficiency_pct);
        setVal('pfMptZ',        d.pf_mpt_impedance_pct);
        setVal('pfMptVoltage',  d.pf_mpt_voltage_hv_kv);
        setVal('pfAuxTrEff',    d.pf_aux_tr_eff_pct);

        updateEfficiencyPreview();

        // Tab 3 — Product selection (cascading dropdowns)
        if (d.battery_product_type) {
            var batSel  = document.getElementById('batteryProductType');
            var modelSel = document.getElementById('pcsModel');
            var cfgSel   = document.getElementById('pcsConfiguration');
            if (batSel) {
                batSel.value = d.battery_product_type;
                onBatteryChange(batSel, modelSel, cfgSel);
            }
            if (d.pcs_configuration && cfgSel) {
                setTimeout(function () {
                    cfgSel.value = d.pcs_configuration;
                    if (cfgSel.value) onPcsConfigChange(cfgSel);
                }, 100);
            }
        }

        // Tab 4 — Operation
        setVal('restSocType',            d.rest_soc);
        setVal('restSocValue',           d.rest_soc_value);
        setVal('cyclePerDay',            d.cycle_per_day);
        setVal('operationDaysPerYear',   d.operation_days_per_year);

        // Augmentation waves
        var augContainer = document.getElementById('augCompactWaves');
        if (augContainer && d.augmentation && d.augmentation.length > 0) {
            augContainer.innerHTML = '';
            augChipId = 0;
            d.augmentation.forEach(function (w) {
                addAugChip(w.year);
            });
        }
    }

    function showCaseBanner(html, state) {
        var banner = document.getElementById('caseBanner');
        if (!banner) return;
        banner.innerHTML = html;
        banner.className = 'case-banner case-banner--' + state;
        banner.style.display = '';
    }

    function escCaseHtml(s) {
        var d = document.createElement('div');
        d.textContent = String(s || '');
        return d.innerHTML;
    }

    // ══════════════════════════════════════════════════════════
    // TAB SWITCHING
    // ══════════════════════════════════════════════════════════
    function initTabs() {
        var tabBar = document.getElementById('tabBar');
        if (!tabBar) return;

        tabBar.addEventListener('click', function (e) {
            var btn = e.target.closest('.tab-btn');
            if (!btn) return;
            var targetId = btn.getAttribute('data-tab');
            switchTab(targetId);
        });
    }

    function switchTab(targetId) {
        // Deactivate all
        document.querySelectorAll('.tab-btn').forEach(function (b) {
            b.classList.remove('active');
        });
        document.querySelectorAll('.tab-content').forEach(function (c) {
            c.classList.remove('active');
        });

        // Activate target
        var tabContent = document.getElementById(targetId);
        if (tabContent) tabContent.classList.add('active');

        var tabBtn = document.querySelector('[data-tab="' + targetId + '"]');
        if (tabBtn) tabBtn.classList.add('active');
    }

    // ══════════════════════════════════════════════════════════
    // EFFICIENCY PRESETS
    // ══════════════════════════════════════════════════════════
    var EFF_PRESETS = {
        'default': {
            hvAcCabling: 0.999, hvTransformer: 0.995, mvAcCabling: 0.999,
            mvTransformer: 0.993, lvCabling: 0.996, pcsEfficiency: 0.985, dcCabling: 0.999,
            appliedDod: 0.99, lossFactors: 0.98802, mbmsConsumption: 0.999,
            branchingPoint: 'MV', auxTrLv: 0.985, auxLineLv: 0.999
        },
        'typical': {
            hvAcCabling: 0.998, hvTransformer: 0.993, mvAcCabling: 0.998,
            mvTransformer: 0.992, lvCabling: 0.996, pcsEfficiency: 0.983, dcCabling: 0.998,
            appliedDod: 0.95, lossFactors: 0.985, mbmsConsumption: 0.998,
            branchingPoint: 'MV', auxTrLv: 0.983, auxLineLv: 0.998
        },
        'conservative': {
            hvAcCabling: 0.997, hvTransformer: 0.990, mvAcCabling: 0.997,
            mvTransformer: 0.990, lvCabling: 0.995, pcsEfficiency: 0.980, dcCabling: 0.997,
            appliedDod: 0.90, lossFactors: 0.980, mbmsConsumption: 0.997,
            branchingPoint: 'MV', auxTrLv: 0.980, auxLineLv: 0.997
        },
        'optimistic': {
            hvAcCabling: 0.9995, hvTransformer: 0.997, mvAcCabling: 0.9995,
            mvTransformer: 0.996, lvCabling: 0.996, pcsEfficiency: 0.988, dcCabling: 0.9995,
            appliedDod: 0.99, lossFactors: 0.992, mbmsConsumption: 0.9995,
            branchingPoint: 'MV', auxTrLv: 0.990, auxLineLv: 0.9995
        }
    };

    function initPresets() {
        document.querySelectorAll('.eff-preset-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var preset = btn.getAttribute('data-preset');
                applyPreset(preset);
                document.querySelectorAll('.eff-preset-btn').forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
            });
        });
    }

    function applyPreset(name) {
        var p = EFF_PRESETS[name];
        if (!p) return;
        Object.keys(p).forEach(function (key) {
            var el = document.getElementById(key);
            if (!el) return;
            if (el.tagName === 'SELECT') {
                el.value = p[key];
            } else {
                el.value = p[key];
            }
        });
        updateEfficiencyPreview();
    }

    // ══════════════════════════════════════════════════════════
    // LIVE EFFICIENCY PREVIEW (Enhanced)
    // ══════════════════════════════════════════════════════════
    function initEfficiencyPreview() {
        var effFields = [
            'hvAcCabling', 'hvTransformer', 'mvAcCabling', 'mvTransformer', 'lvCabling',
            'pcsEfficiency', 'dcCabling', 'appliedDod', 'lossFactors', 'mbmsConsumption',
            'auxTrLv', 'auxLineLv'
        ];
        effFields.forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.addEventListener('input', updateEfficiencyPreview);
        });
        var bpSel = document.getElementById('branchingPoint');
        if (bpSel) bpSel.addEventListener('change', updateEfficiencyPreview);

        initPresets();
        updateEfficiencyPreview();
    }

    function getNumVal(id, fallback) {
        var el = document.getElementById(id);
        if (!el) return fallback;
        var v = parseFloat(el.value);
        return isNaN(v) ? fallback : v;
    }

    function updateEfficiencyPreview() {
        var hvAc   = getNumVal('hvAcCabling',    0.999);
        var hvTr   = getNumVal('hvTransformer',  0.995);
        var mvAc   = getNumVal('mvAcCabling',    0.999);
        var mvTr   = getNumVal('mvTransformer',   0.993);
        var lvCab  = getNumVal('lvCabling',       0.996);
        var pcs    = getNumVal('pcsEfficiency',  0.985);
        var dcCab  = getNumVal('dcCabling',      0.999);
        var dod    = getNumVal('appliedDod',     0.99);
        var loss   = getNumVal('lossFactors',    0.98802);
        var mbms   = getNumVal('mbmsConsumption',0.999);
        var auxTr  = getNumVal('auxTrLv',        0.985);
        var auxLn  = getNumVal('auxLineLv',       0.999);

        var bp = 'MV';
        var bpEl = document.getElementById('branchingPoint');
        if (bpEl) bp = bpEl.value;

        // --- Calculations matching backend exactly ---
        // Total Bat-POI: product of all 6 system stages
        var totalBatPoi = hvAc * hvTr * mvAc * mvTr * lvCab * pcs * dcCab;

        // Aux efficiency — path depends on branching point
        var totalDcToAux;
        var auxPathStages; // for diagram rendering
        if (bp === 'LV') {
            // LV: DC cable → PCS → LV Cable → Aux Tr → Aux Line
            auxPathStages = [
                { label: 'DC Cable', eff: dcCab, icon: 'cable' },
                { label: 'PCS',      eff: pcs,   icon: 'pcs' },
                { label: 'LV Cable', eff: lvCab, icon: 'cable' },
                { label: 'Aux TR',   eff: auxTr, icon: 'transformer' },
                { label: 'Aux Line', eff: auxLn, icon: 'cable' },
            ];
            totalDcToAux = dcCab * pcs * lvCab * auxTr * auxLn;
        } else if (bp === 'HV') {
            // HV: DC cable → PCS → LV Cable → MV TR → MV Cable → HV TR → Aux Tr → Aux Line
            auxPathStages = [
                { label: 'DC Cable', eff: dcCab, icon: 'cable' },
                { label: 'PCS',      eff: pcs,   icon: 'pcs' },
                { label: 'LV Cable', eff: lvCab, icon: 'cable' },
                { label: 'MV TR',    eff: mvTr,  icon: 'transformer' },
                { label: 'MV Cable', eff: mvAc,  icon: 'cable' },
                { label: 'HV TR',    eff: hvTr,  icon: 'transformer' },
                { label: 'Aux TR',   eff: auxTr, icon: 'transformer' },
                { label: 'Aux Line', eff: auxLn, icon: 'cable' },
            ];
            totalDcToAux = dcCab * pcs * lvCab * mvTr * mvAc * hvTr * auxTr * auxLn;
        } else {
            // MV (default): DC cable → PCS → LV Cable → MV TR → MV Cable → Aux Tr → Aux Line
            auxPathStages = [
                { label: 'DC Cable', eff: dcCab, icon: 'cable' },
                { label: 'PCS',      eff: pcs,   icon: 'pcs' },
                { label: 'LV Cable', eff: lvCab, icon: 'cable' },
                { label: 'MV TR',    eff: mvTr,  icon: 'transformer' },
                { label: 'MV Cable', eff: mvAc,  icon: 'cable' },
                { label: 'Aux TR',   eff: auxTr, icon: 'transformer' },
                { label: 'Aux Line', eff: auxLn, icon: 'cable' },
            ];
            totalDcToAux = dcCab * pcs * lvCab * mvTr * mvAc * auxTr * auxLn;
        }

        // Append custom aux stages
        var customStageEffProduct = 1.0;
        for (var cs = 1; cs <= MAX_AUX_STAGES; cs++) {
            var csNameEl = document.getElementById('auxStageName_' + cs);
            var csEffEl  = document.getElementById('auxStageEff_' + cs);
            if (!csNameEl || !csEffEl) continue;
            var csName = csNameEl.value || ('Custom ' + cs);
            var csEff  = parseFloat(csEffEl.value);
            if (isNaN(csEff) || csEff <= 0) csEff = 1.0;
            auxPathStages.push({ label: csName, eff: csEff, icon: 'custom' });
            customStageEffProduct *= csEff;
        }
        totalDcToAux *= customStageEffProduct;

        // Battery loss factor
        var totalBatLoss = dod * loss * mbms;

        // Total system efficiency
        var totalSystemEff = totalBatPoi * totalBatLoss;

        // --- Update preview boxes ---
        setEffDisplay('totalBatPoiEff', (totalBatPoi * 100).toFixed(2) + '%', totalBatPoi);
        setEffDisplay('totalBatLoss',   (totalBatLoss * 100).toFixed(3) + '%', totalBatLoss);
        setEffDisplay('dcToAuxEff',     (totalDcToAux * 100).toFixed(2) + '%', totalDcToAux);
        setEffDisplay('totalSystemEff', (totalSystemEff * 100).toFixed(2) + '%', totalSystemEff);

        var totalLoss = 1 - totalSystemEff;
        setEffDisplay('totalLossPercent', (totalLoss * 100).toFixed(2) + '%', totalLoss, true);

        // --- Update main chain diagram ---
        updateChainDiagram(dcCab, pcs, lvCab, mvTr, mvAc, hvTr, hvAc);

        // --- Update aux chain diagram ---
        updateAuxChainDiagram(auxPathStages, totalDcToAux);

        // --- Update per-field loss tags ---
        updateLossTag('loss-hvAcCabling',    hvAc);
        updateLossTag('loss-hvTransformer',  hvTr);
        updateLossTag('loss-mvAcCabling',    mvAc);
        updateLossTag('loss-mvTransformer',   mvTr);
        updateLossTag('loss-lvCabling',       lvCab);
        updateLossTag('loss-pcsEfficiency',  pcs);
        updateLossTag('loss-dcCabling',      dcCab);
        updateLossTag('loss-appliedDod',     dod);
        updateLossTag('loss-lossFactors',    loss);
        updateLossTag('loss-mbmsConsumption',mbms);
        updateLossTag('loss-auxTrLv',        auxTr);
        updateLossTag('loss-auxLineLv',      auxLn);

        // --- Update waterfall bar ---
        updateWaterfallBar(dcCab, pcs, lvCab, mvTr, mvAc, hvTr, hvAc, dod, loss, mbms);

        // --- Update formula breakdown ---
        updateFormulaBreakdown(dcCab, pcs, lvCab, mvTr, mvAc, hvTr, hvAc, dod, loss, mbms, bp, totalBatPoi, totalBatLoss, totalSystemEff, totalDcToAux);
    }

    function setEffDisplay(id, text, val, invertColors) {
        var el = document.getElementById(id);
        if (!el) return;
        el.textContent = text;
        el.className = 'eff-item__value';
        if (invertColors) {
            if (val < 0.03)       el.classList.add('good');
            else if (val < 0.06)  el.classList.add('warn');
            else                  el.classList.add('bad');
        } else {
            if (val >= 0.96)      el.classList.add('good');
            else if (val >= 0.93) el.classList.add('warn');
            else                  el.classList.add('bad');
        }
    }

    // ══════════════════════════════════════════════════════════
    // CHAIN DIAGRAM UPDATE
    // ══════════════════════════════════════════════════════════
    function updateChainDiagram(dcCab, pcs, lvCab, mvTr, mvAc, hvTr, hvAc) {
        var stages = [
            { loss: 'chain-dcCabling', val: 'chain-val-dcCabling', eff: dcCab },
            { loss: 'chain-pcs',       val: 'chain-val-pcs',       eff: pcs },
            { loss: 'chain-lvCab',     val: 'chain-val-lvCab',     eff: lvCab },
            { loss: 'chain-mvTr',      val: 'chain-val-mvTr',      eff: mvTr },
            { loss: 'chain-mvAc',      val: 'chain-val-mvAc',      eff: mvAc },
            { loss: 'chain-hvTr',      val: 'chain-val-hvTr',      eff: hvTr },
            { loss: 'chain-hvAc',      val: 'chain-val-hvAc',      eff: hvAc },
        ];

        var cumulative = 100.0;
        stages.forEach(function (s) {
            var lossEl = document.getElementById(s.loss);
            var valEl = document.getElementById(s.val);
            var lossAmt = cumulative * (1 - s.eff);
            cumulative = cumulative * s.eff;
            if (lossEl) lossEl.textContent = '-' + lossAmt.toFixed(2) + '%';
            if (valEl) valEl.textContent = cumulative.toFixed(1) + '%';
        });

        var poiEl = document.getElementById('chain-val-poi');
        if (poiEl) poiEl.textContent = cumulative.toFixed(1) + '%';
    }

    // ══════════════════════════════════════════════════════════
    // AUX CHAIN DIAGRAM (Battery → AUX Load)
    // ══════════════════════════════════════════════════════════
    var AUX_SVG_ICONS = {
        battery: '<svg viewBox="0 0 32 32" width="24" height="24"><rect x="4" y="8" width="24" height="18" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><rect x="12" y="4" width="8" height="4" rx="1" fill="currentColor"/><rect x="8" y="14" width="6" height="6" rx="1" fill="currentColor" opacity="0.5"/><rect x="16" y="14" width="6" height="6" rx="1" fill="currentColor" opacity="0.3"/></svg>',
        cable: '<svg viewBox="0 0 32 32" width="24" height="24"><path d="M4 16h6M22 16h6" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/><path d="M10 10c3 0 3 12 6 12s3-12 6-12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
        pcs: '<svg viewBox="0 0 32 32" width="24" height="24"><rect x="4" y="6" width="24" height="20" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M10 20l4-7h4l4 7" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 13l4 7h4l4-7" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.4"/></svg>',
        transformer: '<svg viewBox="0 0 32 32" width="24" height="24"><circle cx="12" cy="16" r="7" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="20" cy="16" r="7" fill="none" stroke="currentColor" stroke-width="2"/><line x1="2" y1="16" x2="5" y2="16" stroke="currentColor" stroke-width="2"/><line x1="27" y1="16" x2="30" y2="16" stroke="currentColor" stroke-width="2"/></svg>',
        auxload: '<svg viewBox="0 0 32 32" width="24" height="24"><rect x="6" y="6" width="20" height="20" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M16 10v5l3 3-3 3v-3l-3-3 3-3z" fill="currentColor" opacity="0.6"/><line x1="10" y1="28" x2="10" y2="30" stroke="currentColor" stroke-width="2"/><line x1="22" y1="28" x2="22" y2="30" stroke="currentColor" stroke-width="2"/></svg>',
        custom: '<svg viewBox="0 0 32 32" width="24" height="24"><rect x="6" y="8" width="20" height="16" rx="3" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="16" cy="16" r="4" fill="none" stroke="currentColor" stroke-width="1.5"/><line x1="12" y1="16" x2="20" y2="16" stroke="currentColor" stroke-width="1"/><line x1="16" y1="12" x2="16" y2="20" stroke="currentColor" stroke-width="1"/></svg>',
    };

    function updateAuxChainDiagram(stages, totalEff) {
        var flowEl = document.getElementById('auxChainFlow');
        var summaryEl = document.getElementById('auxChainEffValue');
        if (!flowEl) return;

        var html = '';

        // Start node: Battery
        html += '<div class="eff-chain__node eff-chain__node--start">';
        html += '<span class="eff-chain__icon">' + AUX_SVG_ICONS.battery + '</span>';
        html += '<div class="eff-chain__node-label">BAT</div>';
        html += '<div class="eff-chain__node-value">100%</div>';
        html += '</div>';

        var cumulative = 100.0;
        for (var i = 0; i < stages.length; i++) {
            var s = stages[i];
            var lossAmt = cumulative * (1 - s.eff);
            cumulative = cumulative * s.eff;
            var isBranch = (s.label === 'Aux TR' || s.label === 'Aux Line');
            var isCustom = (s.icon === 'custom');
            var nodeClass = 'eff-chain__node';
            if (isBranch || isCustom) nodeClass += ' eff-chain__node--branch';

            // Arrow
            html += '<div class="eff-chain__arrow"><span class="eff-chain__loss">-' + lossAmt.toFixed(2) + '%</span></div>';

            // Node
            html += '<div class="' + nodeClass + '">';
            html += '<span class="eff-chain__icon">' + (AUX_SVG_ICONS[s.icon] || AUX_SVG_ICONS.custom) + '</span>';
            html += '<div class="eff-chain__node-label">' + s.label + '</div>';
            html += '<div class="eff-chain__node-value">' + cumulative.toFixed(1) + '%</div>';
            html += '</div>';
        }

        // End node: AUX Load
        html += '<div class="eff-chain__arrow"><span class="eff-chain__loss"></span></div>';
        html += '<div class="eff-chain__node eff-chain__node--end">';
        html += '<span class="eff-chain__icon">' + AUX_SVG_ICONS.auxload + '</span>';
        html += '<div class="eff-chain__node-label">AUX</div>';
        html += '<div class="eff-chain__node-value">' + cumulative.toFixed(1) + '%</div>';
        html += '</div>';

        flowEl.innerHTML = html;

        if (summaryEl) {
            summaryEl.textContent = (totalEff * 100).toFixed(2) + '%';
        }
    }

    // ══════════════════════════════════════════════════════════
    // CUSTOM AUX STAGES (+ button)
    // ══════════════════════════════════════════════════════════
    window.addAuxStage = function () {
        if (auxStageCount >= MAX_AUX_STAGES) {
            alert('Maximum ' + MAX_AUX_STAGES + ' custom auxiliary stages allowed.');
            return;
        }
        auxStageCount++;
        var idx = auxStageCount;
        var container = document.getElementById('auxStagesContainer');
        if (!container) return;

        var div = document.createElement('div');
        div.className = 'aux-stage';
        div.id = 'auxStage-' + idx;
        div.innerHTML =
            '<div class="form-group aux-stage__name-input">' +
                '<label for="auxStageName_' + idx + '">Stage Name</label>' +
                '<input type="text" id="auxStageName_' + idx + '" placeholder="e.g. Step-down TR" value="Custom Stage ' + idx + '" />' +
            '</div>' +
            '<div class="form-group aux-stage__eff-input">' +
                '<label for="auxStageEff_' + idx + '">Efficiency</label>' +
                '<input type="number" id="auxStageEff_' + idx + '" value="0.995" min="0.9" max="1.0" step="0.0001" />' +
            '</div>' +
            '<button type="button" class="aux-stage__remove" onclick="removeAuxStage(' + idx + ')" title="Remove stage">&times;</button>';

        container.appendChild(div);

        // Attach live update listeners
        var nameEl = document.getElementById('auxStageName_' + idx);
        var effEl  = document.getElementById('auxStageEff_' + idx);
        if (nameEl) nameEl.addEventListener('input', updateEfficiencyPreview);
        if (effEl) effEl.addEventListener('input', updateEfficiencyPreview);

        var addBtn = document.getElementById('addAuxStageBtn');
        if (addBtn) addBtn.disabled = (auxStageCount >= MAX_AUX_STAGES);

        updateEfficiencyPreview();
    };

    window.removeAuxStage = function (idx) {
        var el = document.getElementById('auxStage-' + idx);
        if (el) el.remove();
        auxStageCount = Math.max(0, auxStageCount - 1);
        var addBtn = document.getElementById('addAuxStageBtn');
        if (addBtn) addBtn.disabled = (auxStageCount >= MAX_AUX_STAGES);
        updateEfficiencyPreview();
    };

    // ══════════════════════════════════════════════════════════
    // PER-FIELD LOSS TAGS
    // ══════════════════════════════════════════════════════════
    function updateLossTag(id, eff) {
        var el = document.getElementById(id);
        if (!el) return;
        var lossPct = ((1 - eff) * 100);
        el.textContent = '-' + lossPct.toFixed(2) + '%';
        el.className = 'eff-loss-tag';
        if (lossPct < 0.5) el.classList.add('loss-low');
        else if (lossPct < 1.5) el.classList.add('loss-mid');
        else el.classList.add('loss-high');
    }

    // ══════════════════════════════════════════════════════════
    // WATERFALL BAR
    // ══════════════════════════════════════════════════════════
    function updateWaterfallBar(dcCab, pcs, lvCab, mvTr, mvAc, hvTr, hvAc, dod, loss, mbms) {
        var segments = [
            { label: 'DC Cable',  eff: dcCab, cls: 'eff-waterfall__seg--dc' },
            { label: 'PCS',       eff: pcs,   cls: 'eff-waterfall__seg--pcs' },
            { label: 'LV Cable',  eff: lvCab, cls: 'eff-waterfall__seg--lvcab' },
            { label: 'MV TR',     eff: mvTr,  cls: 'eff-waterfall__seg--mvtr' },
            { label: 'MV Cable',  eff: mvAc,  cls: 'eff-waterfall__seg--mvac' },
            { label: 'HV TR',     eff: hvTr,  cls: 'eff-waterfall__seg--hvtr' },
            { label: 'HV Cable',  eff: hvAc,  cls: 'eff-waterfall__seg--hvac' },
            { label: 'DoD',       eff: dod,   cls: 'eff-waterfall__seg--dod' },
            { label: 'Loss F.',   eff: loss,  cls: 'eff-waterfall__seg--loss' },
            { label: 'MBMS',      eff: mbms,  cls: 'eff-waterfall__seg--mbms' },
        ];

        var totalEff = 1.0;
        segments.forEach(function (s) { totalEff *= s.eff; });
        var totalLossPct = (1 - totalEff) * 100;
        var remainingPct = totalEff * 100;

        var barEl = document.getElementById('waterfallBar');
        var legendEl = document.getElementById('waterfallLegend');
        if (!barEl || !legendEl) return;

        var barHtml = '';
        var legendHtml = '';
        var cumLoss = 0;

        // Loss segments
        segments.forEach(function (s) {
            var lossPct = (1 - s.eff) * 100;
            if (lossPct < 0.001) return; // skip negligible
            var widthPct = lossPct; // relative to 100%
            barHtml += '<div class="eff-waterfall__seg ' + s.cls + '" style="width:' + widthPct + '%" title="' + s.label + ': -' + lossPct.toFixed(3) + '%">';
            if (widthPct > 1.5) barHtml += '-' + lossPct.toFixed(1) + '%';
            barHtml += '</div>';
            cumLoss += lossPct;
        });

        // Remaining (delivered) segment
        barHtml += '<div class="eff-waterfall__seg eff-waterfall__seg--remaining" style="width:' + remainingPct + '%" title="Delivered: ' + remainingPct.toFixed(2) + '%">';
        barHtml += remainingPct.toFixed(1) + '%';
        barHtml += '</div>';

        barEl.innerHTML = barHtml;

        // Legend
        legendHtml = '<div class="eff-waterfall__legend-item"><span class="eff-waterfall__legend-dot" style="background:var(--color-success);"></span>Delivered ' + remainingPct.toFixed(1) + '%</div>';
        segments.forEach(function (s) {
            var lossPct = (1 - s.eff) * 100;
            if (lossPct < 0.001) return;
            var color = getComputedStyle(document.documentElement).getPropertyValue('--color-danger') || '#EF5350';
            legendHtml += '<div class="eff-waterfall__legend-item"><span class="eff-waterfall__legend-dot" style="background:' + getCssForClass(s.cls) + ';"></span>' + s.label + ' -' + lossPct.toFixed(3) + '%</div>';
        });
        legendEl.innerHTML = legendHtml;
    }

    function getCssForClass(cls) {
        var map = {
            'eff-waterfall__seg--dc':    '#5C6BC0',
            'eff-waterfall__seg--pcs':   '#AB47BC',
            'eff-waterfall__seg--lvcab': '#7E57C2',
            'eff-waterfall__seg--mvtr':  '#EF5350',
            'eff-waterfall__seg--mvac':  '#FF7043',
            'eff-waterfall__seg--hvtr':  '#FFA726',
            'eff-waterfall__seg--hvac':  '#FFCA28',
            'eff-waterfall__seg--dod':   '#78909C',
            'eff-waterfall__seg--loss':  '#8D6E63',
            'eff-waterfall__seg--mbms':  '#90A4AE',
        };
        return map[cls] || '#999';
    }

    // ══════════════════════════════════════════════════════════
    // FORMULA BREAKDOWN (toggle panel for engineers)
    // ══════════════════════════════════════════════════════════
    window.toggleEffFormula = function () {
        var panel = document.getElementById('effFormulaPanel');
        var btn = document.querySelector('.eff-formula-btn');
        if (!panel) return;
        if (panel.style.display === 'none') {
            panel.style.display = 'block';
            if (btn) btn.innerHTML = '&#9650; Hide Calculation Breakdown';
        } else {
            panel.style.display = 'none';
            if (btn) btn.innerHTML = '&#9660; Show Calculation Breakdown';
        }
    };

    function fmtEff(v) { return (v * 100).toFixed(3) + '%'; }
    function fmtVal(v) { return v.toFixed(6); }

    function updateFormulaBreakdown(dcCab, pcs, lvCab, mvTr, mvAc, hvTr, hvAc, dod, loss, mbms, bp, totalBatPoi, totalBatLoss, totalSystemEff, totalDcToAux) {
        // Bat-POI formula
        var batPoiEl = document.getElementById('formulaBatPoi');
        if (batPoiEl) {
            batPoiEl.innerHTML =
                '<span class="ef-label">DC Cable</span> × <span class="ef-label">PCS</span> × <span class="ef-label">LV Cable</span> × <span class="ef-label">MV TR</span> × <span class="ef-label">MV Cable</span> × <span class="ef-label">HV TR</span> × <span class="ef-label">HV Cable</span><br>' +
                '<span class="ef-val">' + fmtVal(dcCab) + '</span> × ' +
                '<span class="ef-val">' + fmtVal(pcs) + '</span> × ' +
                '<span class="ef-val">' + fmtVal(lvCab) + '</span> × ' +
                '<span class="ef-val">' + fmtVal(mvTr) + '</span> × ' +
                '<span class="ef-val">' + fmtVal(mvAc) + '</span> × ' +
                '<span class="ef-val">' + fmtVal(hvTr) + '</span> × ' +
                '<span class="ef-val">' + fmtVal(hvAc) + '</span>' +
                ' = <strong>' + fmtEff(totalBatPoi) + '</strong>';
        }

        // Battery loss formula
        var batLossEl = document.getElementById('formulaBatLoss');
        if (batLossEl) {
            batLossEl.innerHTML =
                '<span class="ef-label">DoD</span> × <span class="ef-label">Loss Factors</span> × <span class="ef-label">MBMS</span><br>' +
                '<span class="ef-val">' + fmtVal(dod) + '</span> × ' +
                '<span class="ef-val">' + fmtVal(loss) + '</span> × ' +
                '<span class="ef-val">' + fmtVal(mbms) + '</span>' +
                ' = <strong>' + fmtEff(totalBatLoss) + '</strong>';
        }

        // Total system formula
        var totalEl = document.getElementById('formulaTotalSys');
        if (totalEl) {
            totalEl.innerHTML =
                '<span class="ef-label">Bat→POI Eff</span> × <span class="ef-label">Battery Loss</span><br>' +
                '<span class="ef-val">' + fmtEff(totalBatPoi) + '</span> × ' +
                '<span class="ef-val">' + fmtEff(totalBatLoss) + '</span>' +
                ' = <strong>' + fmtEff(totalSystemEff) + '</strong>';
        }

        // DC-to-Aux formula
        var auxEl = document.getElementById('formulaDcToAux');
        var pathEl = document.getElementById('formulaAuxPath');
        if (pathEl) pathEl.textContent = bp;
        if (auxEl) {
            var parts, vals;
            if (bp === 'LV') {
                parts = ['DC Cable', 'PCS', 'LV Cable', 'Aux TR', 'Aux Line'];
                vals = [dcCab, pcs, lvCab];
            } else if (bp === 'HV') {
                parts = ['DC Cable', 'PCS', 'LV Cable', 'MV TR', 'MV Cable', 'HV TR', 'Aux TR', 'Aux Line'];
                vals = [dcCab, pcs, lvCab, mvTr, mvAc, hvTr];
            } else {
                parts = ['DC Cable', 'PCS', 'LV Cable', 'MV TR', 'MV Cable', 'Aux TR', 'Aux Line'];
                vals = [dcCab, pcs, lvCab, mvTr, mvAc];
            }
            // Add aux stages (read from inputs)
            var auxTrV = getNumVal('auxTrLv', 0.985);
            var auxLnV = getNumVal('auxLineLv', 0.999);
            vals.push(auxTrV, auxLnV);

            var html = parts.map(function (p) { return '<span class="ef-label">' + p + '</span>'; }).join(' × ') + '<br>';
            html += vals.map(function (v) { return '<span class="ef-val">' + fmtVal(v) + '</span>'; }).join(' × ');
            html += ' = <strong>' + fmtEff(totalDcToAux) + '</strong>';
            auxEl.innerHTML = html;
        }
    }

    // ══════════════════════════════════════════════════════════
    // PRODUCT DROPDOWNS (cascading PCS model → configuration)
    // ══════════════════════════════════════════════════════════
    var allPcsConfigs = [];   // cached from API

    function loadProductOptions() {
        var batSel    = document.getElementById('batteryProductType');
        var modelSel  = document.getElementById('pcsModel');
        var cfgSel    = document.getElementById('pcsConfiguration');

        fetch('/api/products')
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(function (data) {
                // ── Battery dropdown ──
                if (batSel && data.battery_products) {
                    batSel.innerHTML = '<option value="">-- Select Battery Product --</option>';
                    data.battery_products.forEach(function (p) {
                        var opt = document.createElement('option');
                        opt.value = p.id;
                        opt.textContent = p.name;
                        opt.dataset.specs = JSON.stringify(p.specs || {});
                        batSel.appendChild(opt);
                    });
                    batSel.addEventListener('change', function () {
                        onBatteryChange(batSel, modelSel, cfgSel);
                    });
                }

                // ── PCS Model dropdown (grouped by manufacturer + model, excluding AC LINK-only LSE) ──
                if (modelSel && data.pcs_configurations) {
                    allPcsConfigs = data.pcs_configurations;
                    populatePcsModelDropdown(modelSel, false);
                    modelSel.addEventListener('change', function () {
                        onPcsModelChange(modelSel, cfgSel);
                    });
                }

                // ── PCS Configuration dropdown (populated on model change) ──
                if (cfgSel) {
                    cfgSel.addEventListener('change', function () {
                        onPcsConfigChange(cfgSel);
                    });
                }

                // ── Set defaults: JF2 0.25 DC LINK, EPC Power M-series, M 5stc + JF2 5.1 x 2sets ──
                if (batSel && !batSel.value) {
                    batSel.value = 'JF2 0.25 DC LINK';
                    if (batSel.value) {
                        onBatteryChange(batSel, modelSel, cfgSel);
                    }
                }
                if (modelSel && !modelSel.value) {
                    modelSel.value = 'EPC Power|M5';
                    if (modelSel.value) {
                        onPcsModelChange(modelSel, cfgSel);
                        // After configs populated, select the specific config
                        setTimeout(function () {
                            if (cfgSel) {
                                cfgSel.value = 'EPC Power M 5stc + JF2 5.1 x 2sets';
                                if (cfgSel.value) {
                                    onPcsConfigChange(cfgSel);
                                }
                            }
                        }, 50);
                    }
                }
            })
            .catch(function (err) {
                console.warn('Could not load product options:', err);
                populateFallbackProducts(batSel, modelSel, cfgSel);
            });
    }

    /**
     * Group PCS configs by manufacturer + model.
     * Returns [{key: "EPC Power|M-series", label: "EPC Power M-series", configs: [...]}]
     */
    function groupPcsModels(configs) {
        var map = {};
        configs.forEach(function (c) {
            var key = c.manufacturer + '|' + c.model;
            if (!map[key]) {
                map[key] = {
                    key: key,
                    label: c.manufacturer + ' ' + c.model,
                    configs: []
                };
            }
            map[key].configs.push(c);
        });
        var groups = [];
        Object.keys(map).forEach(function (k) { groups.push(map[k]); });
        return groups;
    }

    /**
     * Populate PCS Model dropdown.
     * @param {boolean} includeAcLink - true to include LSE (AC LINK only), false to exclude
     */
    function populatePcsModelDropdown(modelSel, includeAcLink) {
        if (!modelSel) return;
        var filtered = includeAcLink
            ? allPcsConfigs
            : allPcsConfigs.filter(function (c) { return !c.ac_link; });
        var groups = groupPcsModels(filtered);
        modelSel.innerHTML = '<option value="">-- Select PCS Model --</option>';
        groups.forEach(function (g) {
            var opt = document.createElement('option');
            opt.value = g.key;
            opt.textContent = g.label;
            modelSel.appendChild(opt);
        });
    }

    /**
     * When Battery product changes:
     * - AC LINK → auto-lock PCS to LSE Inverter
     * - Otherwise → restore normal PCS model dropdown
     */
    function onBatteryChange(batSel, modelSel, cfgSel) {
        var isAcLink = batSel.value && batSel.value.indexOf('AC LINK') !== -1;

        if (isAcLink) {
            // Lock PCS to LSE Inverter
            populatePcsModelDropdown(modelSel, true);
            // Auto-select LSE
            var lseKey = 'LSE|Inverter (Built-in)';
            modelSel.value = lseKey;
            modelSel.disabled = true;
            // Trigger config population
            onPcsModelChange(modelSel, cfgSel);
        } else {
            // Restore normal dropdown (exclude LSE)
            var prevModel = modelSel.value;
            modelSel.disabled = false;
            populatePcsModelDropdown(modelSel, false);
            // Try to restore previous selection if it still exists
            if (prevModel) {
                modelSel.value = prevModel;
                if (!modelSel.value) {
                    // Previous selection was LSE, reset
                    cfgSel.innerHTML = '<option value="">-- Select PCS model first --</option>';
                    cfgSel.disabled = true;
                    clearTopology();
                } else {
                    // Refresh configs — battery change may affect compatible configs
                    onPcsModelChange(modelSel, cfgSel);
                }
            }
        }
        updateSpecCard();
    }

    /** When PCS model changes → populate configuration dropdown */
    function onPcsModelChange(modelSel, cfgSel) {
        if (!cfgSel) return;
        var modelKey = modelSel.value;
        cfgSel.innerHTML = '';

        if (!modelKey) {
            cfgSel.innerHTML = '<option value="">-- Select PCS model first --</option>';
            cfgSel.disabled = true;
            clearTopology();
            return;
        }

        // Detect selected battery product family (JF2 or JF3)
        var batSel = document.getElementById('batteryProductType');
        var batVal = batSel ? batSel.value : '';
        var batFamily = '';
        if (batVal.indexOf('JF2') !== -1) batFamily = 'JF2';
        else if (batVal.indexOf('JF3') !== -1) batFamily = 'JF3';

        // Filter configs matching selected model AND compatible battery
        var filtered = allPcsConfigs.filter(function (c) {
            if ((c.manufacturer + '|' + c.model) !== modelKey) return false;
            // If config specifies a battery, it must match selected battery family
            if (c.battery && batFamily && c.battery !== batFamily) return false;
            return true;
        });

        cfgSel.innerHTML = '<option value="">-- Select Configuration --</option>';
        filtered.forEach(function (c) {
            var opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = c.name;
            opt.dataset.linksPerPcs = c.links_per_pcs || 0;
            opt.dataset.stringsPerPcs = c.strings_per_pcs || 0;
            opt.dataset.manufacturer = c.manufacturer || '';
            opt.dataset.model = c.model || '';
            cfgSel.appendChild(opt);
        });
        cfgSel.disabled = false;

        // Auto-select if only one config
        if (filtered.length === 1) {
            cfgSel.selectedIndex = 1;
            onPcsConfigChange(cfgSel);
        } else {
            clearTopology();
        }
    }

    /** When PCS configuration changes → render topology + show specs */
    function onPcsConfigChange(cfgSel) {
        var opt = cfgSel.options[cfgSel.selectedIndex];
        if (!opt || !opt.value) {
            clearTopology();
            return;
        }

        var links   = parseInt(opt.dataset.linksPerPcs, 10) || 0;
        var strings = parseInt(opt.dataset.stringsPerPcs, 10) || 0;
        var mfr     = opt.dataset.manufacturer || '';
        var model   = opt.dataset.model || '';

        renderTopology(links, strings, mfr, model, opt.textContent);

        // Also show spec card with PCS info
        showPcsSpecCard(mfr, model, strings, links, opt.textContent);
    }

    function clearTopology() {
        var container = document.getElementById('topologyDiagram');
        var legend    = document.getElementById('topologyLegend');
        var hint      = document.querySelector('.topology-hint');
        if (container) container.innerHTML = '';
        if (legend) legend.style.display = 'none';
        if (hint) hint.style.display = '';
    }

    /** Show combined Battery + PCS specs in the product spec card */
    function showPcsSpecCard(mfr, model, strings, links, configName) {
        updateSpecCard();
    }

    /** Build the combined spec card from current Battery + PCS selections */
    function updateSpecCard() {
        var card = document.getElementById('productSpecCard');
        var list = document.getElementById('productSpecList');
        if (!card || !list) return;

        var html = '';

        // ── Battery section ──
        var batSel = document.getElementById('batteryProductType');
        if (batSel && batSel.value) {
            var batOpt = batSel.options[batSel.selectedIndex];
            var batSpecs = {};
            try { batSpecs = JSON.parse(batOpt.dataset.specs || '{}'); } catch (e) { /* noop */ }

            html += '<div class="spec-section-title spec-section-title--bat">Battery Product</div>';
            html += '<table class="spec-table"><tbody>';
            html += specRow('Product', batSel.value);
            if (batSpecs.nameplate_energy_mwh) html += specRow('Nameplate Energy', batSpecs.nameplate_energy_mwh + ' MWh');
            if (batSpecs.rack_energy_kwh) html += specRow('Rack Energy', batSpecs.rack_energy_kwh + ' kWh');
            if (batSpecs.module_type && batSpecs.module_type !== 'NA') html += specRow('Module Type', batSpecs.module_type);
            if (batSpecs.gen) html += specRow('Generation', batSpecs.gen);
            html += '</tbody></table>';
        }

        // ── PCS section ──
        var cfgSel = document.getElementById('pcsConfiguration');
        if (cfgSel && cfgSel.value) {
            var opt = cfgSel.options[cfgSel.selectedIndex];
            var mfr     = opt.dataset.manufacturer || '';
            var model   = opt.dataset.model || '';
            var strings = opt.dataset.stringsPerPcs || '';
            var links   = opt.dataset.linksPerPcs || '';

            var isLse = (mfr === 'LSE');
            html += '<div class="spec-section-title spec-section-title--pcs">' + (isLse ? 'PCS (Built-in)' : 'PCS System') + '</div>';
            html += '<table class="spec-table"><tbody>';
            if (isLse) {
                html += specRow('Type', 'Inverter Built-in (AC LINK)');
                html += specRow('AC LINKs / MVT', links);
                html += specRow('Configuration', cfgSel.value);
            } else {
                html += specRow('Manufacturer', mfr);
                html += specRow('Model', model);
                html += specRow('Configuration', cfgSel.value);
                html += specRow('Inv. Strings / PCS', strings);
                html += specRow('LINKs / PCS', links);
                if (parseInt(strings, 10) > 1) {
                    var hw = 'M' + (parseInt(strings, 10) * 2);
                    html += specRow('Hardware Block', hw + ' (' + 'M' + strings + ' + M' + strings + ')');
                }
            }
            html += '</tbody></table>';
        }

        if (!html) {
            card.classList.remove('visible');
            return;
        }

        list.innerHTML = html;
        card.classList.add('visible');
    }

    function specRow(label, value) {
        return '<tr><td>' + escSvg(label) + '</td><td>' + escSvg(String(value)) + '</td></tr>';
    }

    // ══════════════════════════════════════════════════════════
    // PCS–BATTERY TOPOLOGY SVG RENDERER
    // ══════════════════════════════════════════════════════════

    /**
     * Render an SVG diagram showing how battery LINKs connect to one PCS.
     * Layout: PCS box on left, connection lines fanning out to LINK boxes on right.
     */
    function renderTopology(linksPerPcs, stringsPerPcs, mfr, model, configLabel) {
        var container = document.getElementById('topologyDiagram');
        var legend    = document.getElementById('topologyLegend');
        var hint      = document.querySelector('.topology-hint');
        if (!container) return;
        if (hint) hint.style.display = 'none';
        if (legend) legend.style.display = 'flex';

        // Detect AC LINK (LSE built-in inverter) → special diagram
        var isAcLink = (mfr === 'LSE');
        if (isAcLink) {
            renderAcLinkTopo(container, linksPerPcs);
            return;
        }

        // Detect EPC Power M-series (M5/M6) → use Transformer Block diagram
        var isMseries = (mfr === 'EPC Power' && (model === 'M5' || model === 'M6'));
        if (isMseries) {
            renderMseriesTopo(container, linksPerPcs, stringsPerPcs);
            return;
        }

        // ── Standard topology (non-M-series) ──
        var pcsW = 120, pcsH = 70;
        var linkW = 100, linkH = 36;
        var gap = 14;
        var linkCount = linksPerPcs || 1;
        var totalLinkH = linkCount * linkH + (linkCount - 1) * gap;
        var svgH = Math.max(totalLinkH + 40, pcsH + 40);
        var svgW = 420;
        var pcsX = 20, pcsY = (svgH - pcsH) / 2;
        var linkStartX = svgW - linkW - 20;
        var linkStartY = (svgH - totalLinkH) / 2;

        var pcsColor = '#A50034', linkColor = '#1565C0', stringColor = '#EF6C00', lineColor = '#B0BEC5';

        var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + svgW + ' ' + svgH + '">';

        // PCS Box
        svg += '<rect x="' + pcsX + '" y="' + pcsY + '" width="' + pcsW + '" height="' + pcsH + '" rx="8" fill="' + pcsColor + '" />';
        svg += '<text x="' + (pcsX + pcsW / 2) + '" y="' + (pcsY + 22) + '" text-anchor="middle" fill="#fff" font-size="11" font-weight="700">PCS</text>';
        svg += '<text x="' + (pcsX + pcsW / 2) + '" y="' + (pcsY + 38) + '" text-anchor="middle" fill="rgba(255,255,255,0.85)" font-size="9">' + escSvg(mfr) + '</text>';
        svg += '<text x="' + (pcsX + pcsW / 2) + '" y="' + (pcsY + 52) + '" text-anchor="middle" fill="rgba(255,255,255,0.85)" font-size="9">' + escSvg(model) + '</text>';

        if (stringsPerPcs > 1) {
            var badgeX = pcsX + pcsW / 2;
            var badgeY = pcsY + pcsH + 4;
            svg += '<rect x="' + (badgeX - 28) + '" y="' + badgeY + '" width="56" height="16" rx="8" fill="' + stringColor + '" />';
            svg += '<text x="' + badgeX + '" y="' + (badgeY + 12) + '" text-anchor="middle" fill="#fff" font-size="8" font-weight="700">' + stringsPerPcs + ' strings</text>';
        }

        var pcsCenterX = pcsX + pcsW;
        var pcsCenterY = pcsY + pcsH / 2;

        for (var i = 0; i < linkCount; i++) {
            var ly = linkStartY + i * (linkH + gap);
            var linkCenterY = ly + linkH / 2;
            var midX = (pcsCenterX + linkStartX) / 2;
            svg += '<path d="M' + pcsCenterX + ',' + pcsCenterY + ' C' + midX + ',' + pcsCenterY + ' ' + midX + ',' + linkCenterY + ' ' + linkStartX + ',' + linkCenterY + '" fill="none" stroke="' + lineColor + '" stroke-width="2" stroke-dasharray="4,3" />';
            svg += '<rect x="' + linkStartX + '" y="' + ly + '" width="' + linkW + '" height="' + linkH + '" rx="6" fill="' + linkColor + '" />';
            svg += '<text x="' + (linkStartX + linkW / 2) + '" y="' + (ly + 15) + '" text-anchor="middle" fill="#fff" font-size="10" font-weight="700">LINK ' + (i + 1) + '</text>';
            svg += '<text x="' + (linkStartX + linkW / 2) + '" y="' + (ly + 28) + '" text-anchor="middle" fill="rgba(255,255,255,0.8)" font-size="8">Battery</text>';
        }

        svg += '<text x="' + (svgW / 2) + '" y="14" text-anchor="middle" fill="#546E7A" font-size="10" font-weight="600">1 PCS → ' + linkCount + ' LINK' + (linkCount > 1 ? 's' : '') + '</text>';
        svg += '</svg>';
        container.innerHTML = svg;
    }

    /**
     * EPC Power M-series Transformer Block topology.
     *
     * Hardware: M10 = M5+M5, M12 = M6+M6, M14 = M7+M7
     * 1 Transformer Block = 2 PCS (Power Blocks) + 1 MVT
     *
     * Layout:
     *   [MVT] ── [ Transformer Block (M10/M12/M14) ]
     *              ├─ PCS 1 (M5/M6/M7) ──→ LINK 1, LINK 2
     *              └─ PCS 2 (M5/M6/M7) ──→ LINK 3, LINK 4
     */
    function renderMseriesTopo(container, linksPerPcs, stringsPerPcs) {
        var hwName = 'M' + (stringsPerPcs * 2);  // M10, M12, M14
        var pcsLabel = 'M' + stringsPerPcs;        // M5, M6, M7
        var linksPerBlock = linksPerPcs * 2;        // total LINKs per Transformer Block

        // Dimensions
        var svgW = 460, pad = 12;
        var pcsW = 90, pcsH = 52;
        var linkW = 86, linkH = 32;
        var mvtW = 56, mvtH = 56;
        var gap = 10;
        var pcsGap = 16;  // vertical gap between the two PCS boxes

        // Calculate heights
        var linksPerSide = linksPerPcs;
        var oneSideH = linksPerSide * linkH + (linksPerSide - 1) * gap;
        var innerH = oneSideH * 2 + pcsGap;
        var tbPad = 10;
        var tbH = innerH + tbPad * 2 + 24; // +24 for header
        var svgH = tbH + 50; // margin for title + note

        // Transformer Block frame
        var tbX = mvtW + 30, tbY = 22;
        var tbW = svgW - tbX - pad;

        // Colors
        var pcsColor   = '#A50034';
        var linkColor  = '#1565C0';
        var mvtColor   = '#37474F';
        var tbBorder   = '#78909C';
        var stringColor = '#EF6C00';
        var lineColor  = '#B0BEC5';

        var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + svgW + ' ' + svgH + '">';

        // Title — emphasize Power Block as the sizing unit
        svg += '<text x="' + (svgW / 2) + '" y="14" text-anchor="middle" fill="#546E7A" font-size="10" font-weight="600">Transformer Block (' + hwName + ') = 2 × Power Block (' + pcsLabel + ') + 1 MVT</text>';

        // Transformer Block dashed border
        svg += '<rect x="' + tbX + '" y="' + tbY + '" width="' + tbW + '" height="' + tbH + '" rx="10" fill="none" stroke="' + tbBorder + '" stroke-width="1.5" stroke-dasharray="6,3" />';
        svg += '<text x="' + (tbX + 8) + '" y="' + (tbY + 14) + '" fill="' + tbBorder + '" font-size="9" font-weight="700">Transformer Block (' + hwName + ')</text>';

        // MVT box (left of Transformer Block)
        var mvtX = pad;
        var mvtY = tbY + (tbH - mvtH) / 2;
        svg += '<rect x="' + mvtX + '" y="' + mvtY + '" width="' + mvtW + '" height="' + mvtH + '" rx="8" fill="' + mvtColor + '" />';
        svg += '<text x="' + (mvtX + mvtW / 2) + '" y="' + (mvtY + 24) + '" text-anchor="middle" fill="#fff" font-size="11" font-weight="700">MVT</text>';
        svg += '<text x="' + (mvtX + mvtW / 2) + '" y="' + (mvtY + 38) + '" text-anchor="middle" fill="rgba(255,255,255,0.7)" font-size="8">1 unit</text>';

        // MVT → TB connection line
        svg += '<line x1="' + (mvtX + mvtW) + '" y1="' + (mvtY + mvtH / 2) + '" x2="' + tbX + '" y2="' + (mvtY + mvtH / 2) + '" stroke="' + tbBorder + '" stroke-width="2" />';

        // Inner layout: 2 PCS rows, each with its LINKs
        // Power Block 1 (p=0) = SOLID — this is the minimum sizing unit
        // Power Block 2 (p=1) = FADED/DASHED — hardware companion, batteries optional
        var contentY = tbY + 24 + tbPad;
        var pcsX = tbX + 14;
        var linkStartX = tbX + tbW - linkW - 10;

        for (var p = 0; p < 2; p++) {
            var isFaded = (p === 1);  // Power Block 2 is faded
            var rowY = contentY + p * (oneSideH + pcsGap);
            var pcsCY = rowY + oneSideH / 2;

            // Styling per block
            var pcsFill     = isFaded ? 'rgba(165,0,52,0.25)' : pcsColor;
            var pcsStroke    = isFaded ? pcsColor : 'none';
            var pcsStrokeW   = isFaded ? '1.5' : '0';
            var pcsDash      = isFaded ? '4,3' : 'none';
            var pcsTextFill  = isFaded ? pcsColor : '#fff';
            var pcsSubText   = isFaded ? 'rgba(165,0,52,0.6)' : 'rgba(255,255,255,0.85)';
            var badgeFill    = isFaded ? 'rgba(239,108,0,0.25)' : stringColor;
            var badgeStroke   = isFaded ? stringColor : 'none';
            var badgeTextFill = isFaded ? stringColor : '#fff';
            var linkFill     = isFaded ? 'rgba(21,101,192,0.2)' : linkColor;
            var linkStroke    = isFaded ? linkColor : 'none';
            var linkStrokeW  = isFaded ? '1.2' : '0';
            var linkDash     = isFaded ? '3,2' : 'none';
            var linkTextMain = isFaded ? linkColor : '#fff';
            var linkTextSub  = isFaded ? 'rgba(21,101,192,0.6)' : 'rgba(255,255,255,0.8)';
            var curveColor   = isFaded ? 'rgba(176,190,197,0.4)' : lineColor;

            // PCS box (centered vertically in its link group)
            var pcsBoxY = pcsCY - pcsH / 2;
            svg += '<rect x="' + pcsX + '" y="' + pcsBoxY + '" width="' + pcsW + '" height="' + pcsH + '" rx="6" fill="' + pcsFill + '" stroke="' + pcsStroke + '" stroke-width="' + pcsStrokeW + '" stroke-dasharray="' + pcsDash + '" />';
            svg += '<text x="' + (pcsX + pcsW / 2) + '" y="' + (pcsBoxY + 18) + '" text-anchor="middle" fill="' + pcsTextFill + '" font-size="10" font-weight="700">PCS ' + (p + 1) + '</text>';
            svg += '<text x="' + (pcsX + pcsW / 2) + '" y="' + (pcsBoxY + 32) + '" text-anchor="middle" fill="' + pcsSubText + '" font-size="8">' + pcsLabel + '</text>';

            // Strings badge
            svg += '<rect x="' + (pcsX + pcsW / 2 - 24) + '" y="' + (pcsBoxY + 38) + '" width="48" height="12" rx="6" fill="' + badgeFill + '" stroke="' + badgeStroke + '" stroke-width="' + (isFaded ? '1' : '0') + '" stroke-dasharray="' + (isFaded ? '2,2' : 'none') + '" />';
            svg += '<text x="' + (pcsX + pcsW / 2) + '" y="' + (pcsBoxY + 48) + '" text-anchor="middle" fill="' + badgeTextFill + '" font-size="7" font-weight="700">' + stringsPerPcs + ' strings</text>';

            // Power Block label (small tag next to PCS)
            if (!isFaded) {
                svg += '<text x="' + (pcsX + pcsW + 4) + '" y="' + (pcsBoxY + 10) + '" fill="' + pcsColor + '" font-size="7" font-weight="700" opacity="0.8">◀ Power Block 1</text>';
                svg += '<text x="' + (pcsX + pcsW + 4) + '" y="' + (pcsBoxY + 19) + '" fill="#78909C" font-size="6">(min. sizing unit)</text>';
            } else {
                svg += '<text x="' + (pcsX + pcsW + 4) + '" y="' + (pcsBoxY + 10) + '" fill="' + pcsColor + '" font-size="7" opacity="0.5">◁ Power Block 2</text>';
                svg += '<text x="' + (pcsX + pcsW + 4) + '" y="' + (pcsBoxY + 19) + '" fill="#78909C" font-size="6" opacity="0.5">(hardware installed)</text>';
            }

            var pcsCenterX = pcsX + pcsW;

            // LINKs for this PCS
            for (var li = 0; li < linksPerSide; li++) {
                var ly = rowY + li * (linkH + gap);
                var linkCY = ly + linkH / 2;
                var linkIdx = p * linksPerSide + li + 1;

                // Curved line
                var midX = (pcsCenterX + linkStartX) / 2;
                svg += '<path d="M' + pcsCenterX + ',' + pcsCY + ' C' + midX + ',' + pcsCY + ' ' + midX + ',' + linkCY + ' ' + linkStartX + ',' + linkCY + '" fill="none" stroke="' + curveColor + '" stroke-width="1.5" stroke-dasharray="4,3" />';

                // LINK box
                svg += '<rect x="' + linkStartX + '" y="' + ly + '" width="' + linkW + '" height="' + linkH + '" rx="5" fill="' + linkFill + '" stroke="' + linkStroke + '" stroke-width="' + linkStrokeW + '" stroke-dasharray="' + linkDash + '" />';
                svg += '<text x="' + (linkStartX + linkW / 2) + '" y="' + (ly + 13) + '" text-anchor="middle" fill="' + linkTextMain + '" font-size="9" font-weight="700">LINK ' + linkIdx + '</text>';
                svg += '<text x="' + (linkStartX + linkW / 2) + '" y="' + (ly + 24) + '" text-anchor="middle" fill="' + linkTextSub + '" font-size="7">Battery</text>';
            }
        }

        // Divider line between the two PCS rows
        var divY = contentY + oneSideH + pcsGap / 2;
        svg += '<line x1="' + (tbX + 8) + '" y1="' + divY + '" x2="' + (tbX + tbW - 8) + '" y2="' + divY + '" stroke="' + tbBorder + '" stroke-width="0.5" stroke-dasharray="3,3" opacity="0.5" />';

        // Bottom note — emphasize Power Block as minimum sizing unit
        svg += '<text x="' + (svgW / 2) + '" y="' + (svgH - 4) + '" text-anchor="middle" fill="#90A4AE" font-size="8" font-style="italic">Min. sizing unit = 1 Power Block (1 PCS + ' + linksPerPcs + ' LINKs) · HW unit = Transformer Block (' + hwName + ')</text>';

        svg += '</svg>';
        container.innerHTML = svg;
    }

    /**
     * AC LINK topology with 3-winding transformer.
     * Secondary 1 → 2 AC LINKs (solid, minimum sizing unit)
     * Secondary 2 → 2 AC LINKs (faded/dashed, hardware expandable)
     * Layout: [MVT] ─ [Pri ‖ Sec1] ─→ AC LINK 1,2 (solid)
     *                      [Sec2] ─→ AC LINK 3,4 (faded)
     */
    function renderAcLinkTopo(container, linksPerMvt) {
        var linksPerSec = linksPerMvt || 2;  // links per secondary winding
        var svgW = 480;
        var linkW = 100, linkH = 38;
        var gap = 10;
        var secGap = 24;
        var groupH = linksPerSec * linkH + (linksPerSec - 1) * gap;
        var totalContentH = groupH * 2 + secGap;
        var svgH = totalContentH + 80;

        var mvtColor  = '#37474F';
        var linkColor = '#1565C0';
        var pcsTag    = '#4CAF50';
        var lineColor = '#B0BEC5';
        var coilColor = '#546E7A';
        var priColor  = '#FF8F00';
        var secColor  = '#1E88E5';

        // ── Positions ──
        var mvtX = 14, mvtW = 56, mvtH = 50;
        var txCenterX = 160;
        var coilR = 18;
        var linkStartX = svgW - linkW - 14;
        var contentTop = 26;
        var mvtCY = contentTop + totalContentH / 2;
        var mvtY = mvtCY - mvtH / 2;

        var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + svgW + ' ' + svgH + '">';

        // Title
        svg += '<text x="' + (svgW / 2) + '" y="14" text-anchor="middle" fill="#546E7A" font-size="10" font-weight="600">3-Winding MVT · Min. unit = 1 Secondary (' + linksPerSec + ' AC LINKs)</text>';

        // ── MVT Box ──
        svg += '<rect x="' + mvtX + '" y="' + mvtY + '" width="' + mvtW + '" height="' + mvtH + '" rx="6" fill="' + mvtColor + '" />';
        svg += '<text x="' + (mvtX + mvtW / 2) + '" y="' + (mvtY + 22) + '" text-anchor="middle" fill="#fff" font-size="11" font-weight="700">MVT</text>';
        svg += '<text x="' + (mvtX + mvtW / 2) + '" y="' + (mvtY + 36) + '" text-anchor="middle" fill="rgba(255,255,255,0.7)" font-size="8">3-Winding</text>';

        var mvtRightX = mvtX + mvtW;

        // ── Transformer Symbol (3 coils) ──
        var priCX = txCenterX - coilR - 2;
        var priCY = mvtCY;
        svg += '<line x1="' + mvtRightX + '" y1="' + mvtCY + '" x2="' + (priCX - coilR) + '" y2="' + priCY + '" stroke="' + lineColor + '" stroke-width="2" />';
        svg += drawCoil(priCX, priCY, coilR, priColor, '1');

        // Secondary 1 (top)
        var sec1CX = txCenterX + coilR + 2;
        var sec1CY = mvtCY - coilR - 6;
        svg += drawCoil(sec1CX, sec1CY, coilR, secColor, '2a');

        // Secondary 2 (bottom) — faded
        var sec2CX = txCenterX + coilR + 2;
        var sec2CY = mvtCY + coilR + 6;
        svg += '<circle cx="' + sec2CX + '" cy="' + sec2CY + '" r="' + coilR + '" fill="none" stroke="' + secColor + '" stroke-width="2" stroke-dasharray="4,3" opacity="0.4" />';
        svg += '<text x="' + sec2CX + '" y="' + (sec2CY + 4) + '" text-anchor="middle" fill="' + secColor + '" font-size="9" font-weight="700" opacity="0.4">2b</text>';

        // Core
        var coreX = txCenterX;
        var coreTop = Math.min(sec1CY - coilR - 4, priCY - coilR - 4);
        var coreBot = Math.max(sec2CY + coilR + 4, priCY + coilR + 4);
        svg += '<line x1="' + coreX + '" y1="' + coreTop + '" x2="' + coreX + '" y2="' + coreBot + '" stroke="' + coilColor + '" stroke-width="3" />';

        // ── Secondary 1 → AC LINKs (SOLID — active sizing unit) ──
        var sec1OutX = sec1CX + coilR;
        var topStartY = contentTop;
        // Label
        svg += '<text x="' + (sec1OutX + 6) + '" y="' + (topStartY - 4) + '" fill="' + secColor + '" font-size="7" font-weight="700">▼ Secondary 1 (min. sizing unit)</text>';
        for (var i = 0; i < linksPerSec; i++) {
            var ly = topStartY + i * (linkH + gap);
            var linkCY = ly + linkH / 2;
            var midX = (sec1OutX + linkStartX) / 2;
            svg += '<path d="M' + sec1OutX + ',' + sec1CY + ' C' + midX + ',' + sec1CY + ' ' + midX + ',' + linkCY + ' ' + linkStartX + ',' + linkCY + '" fill="none" stroke="' + lineColor + '" stroke-width="1.5" stroke-dasharray="4,3" />';
            svg += renderAcLinkBox(linkStartX, ly, linkW, linkH, (i + 1), linkColor, pcsTag, false);
        }

        // ── Secondary 2 → AC LINKs (FADED — expandable hardware) ──
        var sec2OutX = sec2CX + coilR;
        var botStartY = contentTop + groupH + secGap;
        // Divider
        var divY = topStartY + groupH + secGap / 2;
        svg += '<line x1="' + (sec1OutX + 4) + '" y1="' + divY + '" x2="' + (linkStartX + linkW) + '" y2="' + divY + '" stroke="' + coilColor + '" stroke-width="0.5" stroke-dasharray="3,3" opacity="0.3" />';
        // Label
        svg += '<text x="' + (sec2OutX + 6) + '" y="' + (botStartY - 4) + '" fill="' + secColor + '" font-size="7" opacity="0.45">▽ Secondary 2 (expandable)</text>';
        for (var j = 0; j < linksPerSec; j++) {
            var ly2 = botStartY + j * (linkH + gap);
            var linkCY2 = ly2 + linkH / 2;
            var midX2 = (sec2OutX + linkStartX) / 2;
            svg += '<path d="M' + sec2OutX + ',' + sec2CY + ' C' + midX2 + ',' + sec2CY + ' ' + midX2 + ',' + linkCY2 + ' ' + linkStartX + ',' + linkCY2 + '" fill="none" stroke="rgba(176,190,197,0.35)" stroke-width="1.5" stroke-dasharray="4,3" />';
            svg += renderAcLinkBox(linkStartX, ly2, linkW, linkH, (linksPerSec + j + 1), linkColor, pcsTag, true);
        }

        // ── Winding diagram ──
        var diagY = coreBot + 14;
        svg += renderWindingDiagram(txCenterX - 40, diagY, priColor, secColor, coilColor);

        // Bottom note
        svg += '<text x="' + (svgW / 2) + '" y="' + (svgH - 3) + '" text-anchor="middle" fill="#90A4AE" font-size="8" font-style="italic">Min. sizing unit = 1 Secondary Winding (' + linksPerSec + ' AC LINKs) · HW max = ' + (linksPerSec * 2) + ' AC LINKs per MVT</text>';

        svg += '</svg>';
        container.innerHTML = svg;
    }

    /** Draw a transformer coil (circle with label) */
    function drawCoil(cx, cy, r, color, label) {
        var s = '';
        s += '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="' + color + '" stroke-width="2.5" />';
        s += '<text x="' + cx + '" y="' + (cy + 4) + '" text-anchor="middle" fill="' + color + '" font-size="9" font-weight="700">' + label + '</text>';
        return s;
    }

    /** Draw an AC LINK box with PCS Built-in badge. faded=true for dashed/transparent style. */
    function renderAcLinkBox(x, y, w, h, idx, linkColor, pcsTag, faded) {
        var s = '';
        if (faded) {
            s += '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="6" fill="rgba(21,101,192,0.15)" stroke="' + linkColor + '" stroke-width="1.2" stroke-dasharray="4,3" />';
            s += '<text x="' + (x + w / 2) + '" y="' + (y + 14) + '" text-anchor="middle" fill="' + linkColor + '" font-size="9" font-weight="700" opacity="0.5">AC LINK ' + idx + '</text>';
            var bw = 58, bh = 13;
            var bx = x + (w - bw) / 2;
            var by = y + 19;
            s += '<rect x="' + bx + '" y="' + by + '" width="' + bw + '" height="' + bh + '" rx="6.5" fill="rgba(76,175,80,0.15)" stroke="' + pcsTag + '" stroke-width="1" stroke-dasharray="2,2" />';
            s += '<text x="' + (bx + bw / 2) + '" y="' + (by + 9.5) + '" text-anchor="middle" fill="' + pcsTag + '" font-size="7" font-weight="700" opacity="0.45">PCS Built-in</text>';
        } else {
            s += '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="6" fill="' + linkColor + '" />';
            s += '<text x="' + (x + w / 2) + '" y="' + (y + 14) + '" text-anchor="middle" fill="#fff" font-size="9" font-weight="700">AC LINK ' + idx + '</text>';
            var bw = 58, bh = 13;
            var bx = x + (w - bw) / 2;
            var by = y + 19;
            s += '<rect x="' + bx + '" y="' + by + '" width="' + bw + '" height="' + bh + '" rx="6.5" fill="' + pcsTag + '" />';
            s += '<text x="' + (bx + bw / 2) + '" y="' + (by + 9.5) + '" text-anchor="middle" fill="#fff" font-size="7" font-weight="700">PCS Built-in</text>';
        }
        return s;
    }

    /** Draw a small 3-winding schematic diagram below the transformer */
    function renderWindingDiagram(x, y, priColor, secColor, coreColor) {
        var s = '';
        var coreX = x + 40;
        var w = 80, h = 36;

        // Background
        s += '<rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" rx="4" fill="#FAFAFA" stroke="#E0E0E0" stroke-width="1" />';

        // Core (two vertical lines)
        s += '<line x1="' + (coreX - 2) + '" y1="' + (y + 6) + '" x2="' + (coreX - 2) + '" y2="' + (y + h - 6) + '" stroke="' + coreColor + '" stroke-width="2" />';
        s += '<line x1="' + (coreX + 2) + '" y1="' + (y + 6) + '" x2="' + (coreX + 2) + '" y2="' + (y + h - 6) + '" stroke="' + coreColor + '" stroke-width="2" />';

        // Primary winding (left bumps)
        var py = y + h / 2;
        for (var p = -1; p <= 1; p++) {
            var by = py + p * 7;
            s += '<path d="M' + (coreX - 4) + ',' + (by - 3.5) + ' Q' + (coreX - 14) + ',' + by + ' ' + (coreX - 4) + ',' + (by + 3.5) + '" fill="none" stroke="' + priColor + '" stroke-width="1.5" />';
        }
        s += '<text x="' + (x + 6) + '" y="' + (py + 3) + '" fill="' + priColor + '" font-size="7" font-weight="700">1</text>';

        // Secondary winding top (right bumps, upper)
        var sy1 = py - 8;
        for (var s1 = -1; s1 <= 0; s1++) {
            var by1 = sy1 + s1 * 7;
            s += '<path d="M' + (coreX + 5) + ',' + (by1 - 3.5) + ' Q' + (coreX + 15) + ',' + by1 + ' ' + (coreX + 5) + ',' + (by1 + 3.5) + '" fill="none" stroke="' + secColor + '" stroke-width="1.5" />';
        }
        s += '<text x="' + (x + w - 14) + '" y="' + (sy1 - 2) + '" fill="' + secColor + '" font-size="7" font-weight="700">2a</text>';

        // Secondary winding bottom (right bumps, lower) — faded
        var sy2 = py + 8;
        for (var s2 = 0; s2 <= 1; s2++) {
            var by2 = sy2 + s2 * 7;
            s += '<path d="M' + (coreX + 5) + ',' + (by2 - 3.5) + ' Q' + (coreX + 15) + ',' + by2 + ' ' + (coreX + 5) + ',' + (by2 + 3.5) + '" fill="none" stroke="' + secColor + '" stroke-width="1.5" opacity="0.35" stroke-dasharray="2,2" />';
        }
        s += '<text x="' + (x + w - 14) + '" y="' + (sy2 + 12) + '" fill="' + secColor + '" font-size="7" font-weight="700" opacity="0.35">2b</text>';

        return s;
    }

    function escSvg(s) {
        return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function populateFallbackProducts(batSel, modelSel, cfgSel) {
        var batProducts = [
            { id: 'JF3 0.25 DC LINK', name: 'JF3 0.25 DC LINK' },
            { id: 'JF2 0.25 DC LINK', name: 'JF2 0.25 DC LINK' },
            { id: 'JF2 0.25 AC LINK', name: 'JF2 0.25 AC LINK' },
        ];

        if (batSel) {
            batSel.innerHTML = '<option value="">-- Select Battery Product --</option>';
            batProducts.forEach(function (p) {
                var opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.name;
                batSel.appendChild(opt);
            });
        }

        // Fallback PCS models
        allPcsConfigs = [
            { id: 'EPC Power M 6stc + JF3 5.5 x 2sets', name: 'EPC Power M 6stc + JF3 5.5 x 2sets', manufacturer: 'EPC Power', model: 'M6', strings_per_pcs: 6, links_per_pcs: 2 },
            { id: 'SMA SCS4600-UP-S+ JF2 5.1 x 3sets', name: 'SMA SCS4600-UP-S+ JF2 5.1 x 3sets', manufacturer: 'SMA', model: 'SCS4600-UP-S', strings_per_pcs: 1, links_per_pcs: 3 },
        ];

        if (modelSel) {
            var groups = groupPcsModels(allPcsConfigs);
            modelSel.innerHTML = '<option value="">-- Select PCS Model --</option>';
            groups.forEach(function (g) {
                var opt = document.createElement('option');
                opt.value = g.key;
                opt.textContent = g.label;
                modelSel.appendChild(opt);
            });
            modelSel.addEventListener('change', function () {
                onPcsModelChange(modelSel, cfgSel);
            });
        }

        if (cfgSel) {
            cfgSel.addEventListener('change', function () {
                onPcsConfigChange(cfgSel);
            });
        }
    }

    function showProductSpecs(selectEl, cardId, listId) {
        var card = document.getElementById(cardId);
        var list = document.getElementById(listId);
        if (!card || !list) return;

        var opt = selectEl.options[selectEl.selectedIndex];
        if (!opt || !opt.value) {
            card.classList.remove('visible');
            return;
        }

        var specs = {};
        try { specs = JSON.parse(opt.dataset.specs || '{}'); } catch (e) { /* noop */ }

        list.innerHTML = '';
        Object.keys(specs).forEach(function (k) {
            var dt = document.createElement('dt');
            dt.textContent = k;
            var dd = document.createElement('dd');
            dd.textContent = specs[k];
            list.appendChild(dt);
            list.appendChild(dd);
        });

        card.classList.add('visible');
    }

    // ══════════════════════════════════════════════════════════
    // AUGMENTATION WAVES (compact chip UI)
    // ══════════════════════════════════════════════════════════
    var augChipId = 0;

    function getAugChipCount() {
        var container = document.getElementById('augCompactWaves');
        return container ? container.querySelectorAll('.aug-chip').length : 0;
    }

    function updateAugAddBtn() {
        var btn = document.getElementById('augCompactAddBtn');
        if (btn) btn.disabled = (getAugChipCount() >= MAX_AUG_WAVES);
    }

    window.addAugChip = function (prefillYear, prefillLinks, prefillEnergy) {
        if (getAugChipCount() >= MAX_AUG_WAVES) {
            alert('Maximum ' + MAX_AUG_WAVES + ' augmentation waves allowed.');
            return;
        }
        // Auto-fill 1st wave year from Oversizing Year
        if (!prefillYear && getAugChipCount() === 0) {
            var osYr = document.getElementById('oversizingYear');
            if (osYr && osYr.value) prefillYear = parseInt(osYr.value, 10);
        }
        augChipId++;
        var idx = augChipId;
        var container = document.getElementById('augCompactWaves');
        if (!container) return;

        var waveNum = getAugChipCount() + 1;
        var yearVal = prefillYear || '';
        var linksVal = prefillLinks || 2;
        var energyVal = prefillEnergy || 0;
        var energyDisplay = energyVal > 0 ? parseFloat(energyVal).toFixed(1) : '—';

        var tr = document.createElement('tr');
        tr.className = 'aug-chip';
        tr.id = 'augChip-' + idx;
        tr.innerHTML =
            '<td class="aug-td-label">Wave ' + waveNum + '</td>' +
            '<td><input type="number" class="aug-input" id="augYear_' + idx + '" ' +
                'value="' + yearVal + '" min="1" max="20" step="1" placeholder="yr" /></td>' +
            '<td>' +
                '<div class="aug-links-ctrl">' +
                '<button type="button" class="aug-adj" onclick="adjustAugLinks(' + idx + ',-2)">\u2212</button>' +
                '<input type="number" class="aug-input aug-chip__links" id="augLinks_' + idx + '" ' +
                    'value="' + linksVal + '" min="2" step="2" onchange="adjustAugLinks(' + idx + ',0)" />' +
                '<button type="button" class="aug-adj" onclick="adjustAugLinks(' + idx + ',2)">+</button>' +
                '</div>' +
            '</td>' +
            '<td class="aug-td-energy" id="augEnergyDisplay_' + idx + '">' + energyDisplay + '</td>' +
            '<td><button type="button" class="aug-remove" onclick="removeAugChip(' + idx + ')">&times;</button></td>' +
            '<input type="hidden" id="augEnergy_' + idx + '" value="' + energyVal + '" />';

        container.appendChild(tr);
        updateAugAddBtn();
        if (!prefillYear) tr.querySelector('input').focus();
    };

    window.adjustAugLinks = function (idx, delta) {
        var inp = document.getElementById('augLinks_' + idx);
        if (!inp) return;
        var val = parseInt(inp.value, 10) || 0;
        val = Math.max(2, val + delta);
        inp.value = val;
        // Update hidden energy + visible display
        var energyInp = document.getElementById('augEnergy_' + idx);
        var energyDisp = document.getElementById('augEnergyDisplay_' + idx);
        if (lastResult && lastResult.battery) {
            var npe = lastResult.battery.nameplate_energy_per_link_mwh || 0;
            var energy = val * npe;
            if (energyInp) energyInp.value = energy.toFixed(3);
            if (energyDisp) energyDisp.textContent = energy.toFixed(1);
        } else {
            if (energyDisp) energyDisp.textContent = '—';
        }
    };

    window.removeAugChip = function (idx) {
        var el = document.getElementById('augChip-' + idx);
        if (el) el.remove();
        // Re-number wave labels
        var container = document.getElementById('augCompactWaves');
        if (container) {
            var chips = container.querySelectorAll('.aug-chip');
            for (var i = 0; i < chips.length; i++) {
                var lbl = chips[i].querySelector('.aug-td-label');
                if (lbl) lbl.textContent = 'Wave ' + (i + 1);
            }
        }
        updateAugAddBtn();
    };

    // Legacy compat — old addAugWave/removeAugWave calls
    window.addAugWave = window.addAugChip;
    window.removeAugWave = window.removeAugChip;

    // ══════════════════════════════════════════════════════════
    // FORM COLLECTION
    // ══════════════════════════════════════════════════════════
    function collectFormData() {
        function val(id)       { var e = document.getElementById(id); return e ? e.value : ''; }
        function num(id, def)  { var v = parseFloat(val(id)); return isNaN(v) ? def : v; }
        function int(id, def)  { var v = parseInt(val(id), 10); return isNaN(v) ? def : v; }

        var payload = {
            // Tab 1
            project_title:         val('projectTitle'),
            customer:              val('customer'),
            project_life:          int('projectLife', 20),
            poi_level:             val('poiLevel'),
            voltage_level_kv:      num('voltageLevel', 0),
            required_power_mw:     num('requiredPower', 100),
            required_energy_mwh:   num('requiredEnergy', 400),
            power_factor:          num('powerFactor', 0.95),
            aux_power_source:      val('auxPowerSource'),
            oversizing_year:       int('oversizingYear', 5),
            link_override:         int('linkOverride', 0),
            application:           val('application'),
            measurement_method:    val('measurementMethod'),
            temperature_c:         num('temperature', 45),
            altitude:              val('altitude'),

            // Tab 2
            hv_ac_cabling:         num('hvAcCabling', 0.999),
            hv_transformer:        num('hvTransformer', 0.995),
            mv_ac_cabling:         num('mvAcCabling', 0.999),
            mv_transformer:        num('mvTransformer', 0.993),
            lv_cabling:            num('lvCabling', 0.996),
            pcs_efficiency:        num('pcsEfficiency', 0.985),
            dc_cabling:            num('dcCabling', 0.999),
            branching_point:       val('branchingPoint'),
            aux_tr_lv:             num('auxTrLv', 0.985),
            aux_line_lv:           num('auxLineLv', 0.999),
            applied_dod:           num('appliedDod', 0.99),
            loss_factors:          num('lossFactors', 0.98802),
            mbms_consumption:      num('mbmsConsumption', 0.999),

            // Tab 3
            battery_product_type:  val('batteryProductType'),
            pcs_configuration:     val('pcsConfiguration'),

            // Tab 4
            rest_soc:              val('restSocType'),
            rest_soc_value:        num('restSocValue', 30),
            cycle_per_day:         num('cyclePerDay', 1),
            operation_days_per_year: int('operationDaysPerYear', 365),

            // Augmentation waves (chip UI)
            augmentation: [],

            // Power Flow equipment parameters (optional, with defaults)
            pf_pcs_voltage_kv:     num('pfPcsVoltage', 0.69),
            pf_lv_r_ohm_per_km:    num('pfLvR', 0.012),
            pf_lv_x_ohm_per_km:    num('pfLvX', 0.018),
            pf_lv_length_km:       num('pfLvLen', 5) / 1000,  // UI shows meters, API expects km
            pf_mvt_capacity_mva:   num('pfMvtCapacity', 100),
            pf_mvt_efficiency_pct: num('pfMvtEff', 98.9),
            pf_mvt_impedance_pct:  num('pfMvtZ', 6.0),
            pf_mv_r_ohm_per_km:    num('pfMvR', 0.115),
            pf_mv_x_ohm_per_km:    num('pfMvX', 0.125),
            pf_mv_length_km:       num('pfMvLen', 2.0),
            pf_mv_voltage_kv:      num('pfMvVoltage', 34.5),
            pf_mpt_capacity_mva:   num('pfMptCapacity', 300),
            pf_mpt_efficiency_pct: num('pfMptEff', 99.65),
            pf_mpt_impedance_pct:  num('pfMptZ', 14.5),
            pf_mpt_voltage_hv_kv:  num('pfMptVoltage', 154),
            pf_aux_tr_eff_pct:     num('pfAuxTrEff', 98.5),
        };

        var augContainer = document.getElementById('augCompactWaves');
        if (augContainer) {
            var chips = augContainer.querySelectorAll('.aug-chip');
            for (var ci = 0; ci < chips.length; ci++) {
                var yearInp = chips[ci].querySelector('input[type="number"]');
                if (!yearInp) continue;
                var augYear = parseInt(yearInp.value, 10);
                if (isNaN(augYear) || augYear < 1) continue;
                var wave = { year: augYear };
                // Include LINK count and energy if available (from auto-recommend)
                var linksInp = chips[ci].querySelector('.aug-chip__links');
                var energyInp = chips[ci].querySelector('input[type="hidden"]');
                if (linksInp) {
                    wave.additional_links = parseInt(linksInp.value, 10) || 0;
                }
                if (energyInp && parseFloat(energyInp.value) > 0) {
                    wave.additional_energy_mwh = parseFloat(energyInp.value);
                }
                payload.augmentation.push(wave);
            }
            // Sort by year ascending
            payload.augmentation.sort(function (a, b) { return a.year - b.year; });
        }

        return payload;
    }

    // ══════════════════════════════════════════════════════════
    // VALIDATION
    // ══════════════════════════════════════════════════════════
    function validateForm(data) {
        var errors = [];
        if (!data.battery_product_type) errors.push('Battery Product Type is required (Tab 3).');
        if (data.required_power_mw <= 0) errors.push('Required Power must be > 0.');
        if (data.required_energy_mwh <= 0) errors.push('Required Energy must be > 0.');
        if (data.power_factor < 0.5 || data.power_factor > 1.0)
            errors.push('Power Factor must be between 0.5 and 1.0.');
        return errors;
    }

    // ══════════════════════════════════════════════════════════
    // CALCULATE
    // ══════════════════════════════════════════════════════════
    window.submitCalculation = function () {
        hideError();
        var data = collectFormData();
        var errors = validateForm(data);
        if (errors.length) {
            showError(errors.join(' '));
            return;
        }

        setLoading(true);

        fetch('/api/calculate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        })
            .then(function (r) {
                if (!r.ok) return r.json().then(function (e) { throw new Error(e.error || 'Server error ' + r.status); });
                return r.json();
            })
            .then(function (result) {
                setLoading(false);
                lastResult = result;
                displayResults(result);
                if (_caseId) {
                    saveCaseResult(collectFormData(), result);
                }
            })
            .catch(function (err) {
                setLoading(false);
                showError(err.message || 'Unknown error. Check backend connection.');
            });
    };

    // ══════════════════════════════════════════════════════════
    // AUTO-SAVE TO CASE
    // ══════════════════════════════════════════════════════════
    function saveCaseResult(inputData, resultData) {
        fetch('/api/cases/' + _caseId, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                input_data: inputData,
                result_data: resultData,
            }),
        })
        .then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            showSavedToast();
        })
        .catch(function (err) {
            console.warn('Auto-save to case failed:', err.message);
            var toast = document.getElementById('savedToast');
            if (toast) {
                toast.textContent = 'Save failed';
                toast.classList.add('visible', 'error');
                setTimeout(function () { toast.classList.remove('visible', 'error'); toast.textContent = 'Saved to case'; }, 4000);
            }
        });
    }

    function showSavedToast() {
        var toast = document.getElementById('savedToast');
        if (!toast) return;
        toast.classList.add('visible');
        setTimeout(function () { toast.classList.remove('visible'); }, 2500);
    }

    // Manual "Save to Case" from bottom action bar
    window._manualSaveToCase = function () {
        if (!_caseId) { alert('No case context. Open a case first.'); return; }
        if (!lastResult) { alert('No calculation results yet. Run Calculate first.'); return; }
        saveCaseResult(collectFormData(), lastResult);
    };

    // ══════════════════════════════════════════════════════════
    // DISPLAY RESULTS
    // ══════════════════════════════════════════════════════════
    function displayResults(result) {
        var section = document.getElementById('results-section');
        if (!section) return;
        section.classList.add('visible');

        // Update auxiliary load tab with calculation results
        updateAuxiliaryDisplay();

        // Scroll to results
        section.scrollIntoView({ behavior: 'smooth', block: 'start' });

        var bat = result.battery;
        var pcs = result.pcs;
        var eff = result.efficiency;
        var rp  = result.reactive_power;
        var rte = result.rte;
        var sum = result.summary || {};

        // ── Hero KPI Cards ──
        setText('res-noPcs',        pcs.no_of_pcs);
        setText('res-noLinks',      bat.no_of_links);
        // Racks as sub-info under LINKs
        var racksSub = document.getElementById('res-noRacksSub');
        if (racksSub) racksSub.textContent = '(' + bat.no_of_racks + ' racks = ' + bat.racks_per_link + ' racks/LINK)';
        // Installed Energy: 3 decimal places + tooltip
        setText('res-instEnergy',   bat.installation_energy_dc_mwh.toFixed(3));
        var instEl = document.getElementById('res-instEnergy');
        if (instEl) instEl.title = bat.nameplate_energy_per_link_mwh + ' MWh × ' + bat.no_of_links + ' LINKs';
        // Usable @POI: 3 decimal places
        setText('res-usableEnergy', bat.dischargeable_energy_poi_mwh.toFixed(3));
        setText('res-duration',     bat.duration_bol_hr.toFixed(2));

        // ── Project Requirements ──
        setText('res-reqPower',    sum.required_power_mw || '—');
        setText('res-reqEnergy',   sum.required_energy_mwh || '—');
        setText('res-reqDuration', sum.duration_hours || '—');
        setText('res-temperature', sum.temperature_c || '—');
        setText('res-altitude',    sum.altitude || '—');
        setHtml('res-auxIncluded', sum.aux_included
            ? '<span class="badge badge--ok">YES</span> (' + (sum.aux_power_source || 'Battery') + ')'
            : '<span class="badge badge--warn">NO</span> (' + (sum.aux_power_source || 'Grid') + ')');
        setHtml('res-augIncluded', sum.augmentation_included
            ? '<span class="badge badge--ok">YES</span>'
            : '<span class="badge badge--warn">NO</span>');

        // ── Battery System ──
        setText('res-productType',       sum.product_type || '—');
        setText('res-detailLinks',       bat.no_of_links);
        setText('res-detailRacks',       bat.no_of_racks);
        setText('res-racksPerLink',      bat.racks_per_link || '—');
        setText('res-powerAtDc',         bat.req_power_dc_mw.toFixed(3));
        // 3 decimal places for energy
        setText('res-detailInstEnergy',  bat.installation_energy_dc_mwh.toFixed(3));
        var detInstEl = document.getElementById('res-detailInstEnergy');
        if (detInstEl) detInstEl.title = bat.nameplate_energy_per_link_mwh + ' MWh × ' + bat.no_of_links + ' LINKs';
        setText('res-detailUsableEnergy', bat.dischargeable_energy_poi_mwh.toFixed(3));
        // CP-rate
        setText('res-cpRate',            bat.cp_rate.toFixed(4));
        // Power & Energy Oversizing
        var reqPow = sum.required_power_mw || 0;
        var reqEne = sum.required_energy_mwh || 0;
        var instPow = bat.no_of_pcs * (pcs.pcs_unit_power_mw || 0);  // installed power @DC
        var powerOversizing = reqPow > 0 ? ((instPow - reqPow) / reqPow * 100) : 0;
        var energyOversizing = reqEne > 0 ? ((bat.dischargeable_energy_poi_mwh - reqEne) / reqEne * 100) : 0;
        setText('res-powerOversizing',   powerOversizing.toFixed(1));
        setText('res-energyOversizing',  energyOversizing.toFixed(1));

        // ── PCS System ──
        setText('res-pcsManufacturer', pcs.manufacturer || '—');
        // Model with stacks info
        var modelLabel = pcs.model || '—';
        if (pcs.strings_per_pcs && pcs.strings_per_pcs > 1) {
            modelLabel += ' (' + pcs.strings_per_pcs + ' Stacks)';
        }
        setText('res-pcsModel',        modelLabel);
        // PCS-level inverter size @25°C = base_power_kva × strings_per_pcs
        var pcsLevelKva = (pcs.base_power_kva && pcs.strings_per_pcs)
            ? (pcs.base_power_kva * pcs.strings_per_pcs) : null;
        setText('res-inverterSize',    pcsLevelKva ? pcsLevelKva.toFixed(0) : '—');
        var invEl = document.getElementById('res-inverterSize');
        if (invEl && pcs.base_power_kva && pcs.strings_per_pcs > 1) {
            invEl.title = pcs.base_power_kva.toFixed(0) + ' kVA/stack × ' + pcs.strings_per_pcs + ' stacks';
        }
        setText('res-deratedPower',    pcs.derated_power_kva ? pcs.derated_power_kva.toFixed(1) : '—');
        setText('res-pcsUnitPower',    pcs.pcs_unit_power_mw ? pcs.pcs_unit_power_mw.toFixed(3) : '—');
        setText('res-detailNoPcs',     pcs.no_of_pcs);
        setText('res-noMvt',           sum.no_of_mvt != null ? sum.no_of_mvt : (bat.no_of_mvt || '—'));
        setText('res-noSkid',          sum.no_of_skid || pcs.no_of_pcs);
        setText('res-linksPerPcs',     pcs.links_per_pcs);
        // F1: M10 order quantity + transformer blocks
        setText('res-noM10Order',      sum.no_of_m10_order != null ? sum.no_of_m10_order : '—');
        setText('res-noTransBlocks',   sum.no_of_transformer_blocks != null ? sum.no_of_transformer_blocks : '—');
        // Show/hide M10 row (only relevant for EPC Power M-system)
        var m10Row = document.getElementById('row-m10Order');
        if (m10Row) m10Row.style.display = sum.no_of_m10_order != null ? '' : 'none';

        // ── Efficiency Summary ──
        setText('res-effBatPoi',  (eff.total_bat_poi_eff * 100).toFixed(2));
        setText('res-effBatLoss', (eff.total_battery_loss_factor * 100).toFixed(2));
        setText('res-effDcAux',   (eff.total_dc_to_aux_eff * 100).toFixed(2));
        setText('res-effTotal',   (eff.total_efficiency * 100).toFixed(2));
        setText('res-rte',        rte ? (rte.system_rte * 100).toFixed(1) : '—');

        // ── Reactive Power ──
        setText('res-apparentPower', rp ? rp.total_apparent_power_poi_kva.toFixed(1) : '—');
        setText('res-pfMv',          rp ? rp.pf_at_mv.toFixed(4) : '—');
        setText('res-availableS',    rp ? rp.available_s_total_kva.toFixed(1) : '—');
        setText('res-gridKvar',      rp ? rp.grid_kvar.toFixed(1) : '—');
        // F2+F5: Update Reactive Power Tab
        updateReactivePowerTab(result);
        var pcsSuf = document.getElementById('res-pcsSufficient');
        if (pcsSuf) {
            var pfData = result.power_flow;
            var isSufficient = pfData ? pfData.is_pcs_sufficient : (rp ? rp.is_pcs_sufficient : null);
            if (isSufficient !== null && isSufficient !== undefined) {
                pcsSuf.innerHTML = isSufficient
                    ? '<span class="badge badge--ok">YES</span>'
                    : '<span class="badge badge--danger">NO</span>';
            }
        }

        // Retention Table (with toggle-able intermediate columns + augmentation)
        var tbody = document.getElementById('retentionTableBody');
        if (tbody && result.retention && result.retention.retention_by_year) {
            var rows = '';
            var byYear = result.retention.retention_by_year;
            // Check which optional columns are visible
            var showDc = document.getElementById('togColDc') && document.getElementById('togColDc').checked;
            var showDcAux = document.getElementById('togColDcAux') && document.getElementById('togColDcAux').checked;
            var showMv = document.getElementById('togColMv') && document.getElementById('togColMv').checked;
            var showThroughput = document.getElementById('togColThroughput') && document.getElementById('togColThroughput').checked;
            var dcStyle = showDc ? '' : 'display:none;';
            var dcAuxStyle = showDcAux ? '' : 'display:none;';
            var mvStyle = showMv ? '' : 'display:none;';
            var throughputStyle = showThroughput ? '' : 'display:none;';

            // Annual Energy Throughput: min(Disch@POI, Required Energy) × Operation Days
            var reqEnergy = parseFloat(result.summary ? result.summary.required_energy_mwh : 0) || 0;
            var opDays = parseFloat(document.getElementById('operationDaysPerYear') ? document.getElementById('operationDaysPerYear').value : 365) || 365;

            // Detect augmentation: check if retention source contains "augmentation"
            var hasAug = result.retention.lookup_source && result.retention.lookup_source.indexOf('augmentation') !== -1;
            var augStyle = hasAug ? '' : 'display:none;';

            // Show/hide augmentation header columns + wave toggles
            var augEls = document.querySelectorAll('.colAug');
            for (var ai = 0; ai < augEls.length; ai++) {
                augEls[ai].style.display = hasAug ? '' : 'none';
            }

            // Per-wave details from backend
            var waveDetails = (hasAug && result.retention.wave_details) ? result.retention.wave_details : null;
            // Determine which waves exist
            var waveKeys = waveDetails ? Object.keys(waveDetails).sort(function(a,b){return +a - +b;}) : [];

            // Hide wave toggle checkboxes for waves that don't exist
            for (var wi = 0; wi <= 3; wi++) {
                var togLabel = document.getElementById('togWave' + wi);
                if (togLabel) {
                    var waveExists = hasAug && waveKeys.indexOf(String(wi)) !== -1;
                    togLabel.parentElement.style.display = waveExists ? '' : 'none';
                }
            }

            // Wave column visibility based on toggle state
            var waveStyles = {};
            for (var wi = 0; wi <= 3; wi++) {
                var togEl = document.getElementById('togWave' + wi);
                var isChecked = togEl ? togEl.checked : true;
                var waveExists = waveKeys.indexOf(String(wi)) !== -1;
                waveStyles[wi] = (hasAug && waveExists && isChecked) ? '' : 'display:none;';
            }

            Object.keys(byYear).sort(function (a, b) { return +a - +b; }).forEach(function (yr) {
                var d = byYear[yr];
                var retLevel = d.retention_pct >= 85 ? 'high' : (d.retention_pct >= 70 ? 'mid' : 'low');

                // Per-wave cells (energy + DC/DC-Aux/MV when toggled + POI)
                var waveCells = '';
                for (var wi = 0; wi <= 3; wi++) {
                    var ws = waveStyles[wi];
                    if (waveDetails && waveDetails[String(wi)] && waveDetails[String(wi)].by_year && waveDetails[String(wi)].by_year[yr]) {
                        var wd = waveDetails[String(wi)].by_year[yr];
                        waveCells += '<td class="colAug colWave' + wi + ' col-aug" style="' + ws + '">' + wd.energy_mwh.toFixed(3) + '</td>';
                        waveCells += '<td class="colAug colWave' + wi + ' colDc col-aug" style="' + ws + (showDc ? '' : 'display:none;') + '">' + (wd.disch_dc_mwh != null ? wd.disch_dc_mwh.toFixed(3) : '—') + '</td>';
                        waveCells += '<td class="colAug colWave' + wi + ' colDcAux col-aug" style="' + ws + (showDcAux ? '' : 'display:none;') + '">' + (wd.disch_dc_aux_mwh != null ? wd.disch_dc_aux_mwh.toFixed(3) : '—') + '</td>';
                        waveCells += '<td class="colAug colWave' + wi + ' colMv col-aug" style="' + ws + (showMv ? '' : 'display:none;') + '">' + (wd.disch_mv_mwh != null ? wd.disch_mv_mwh.toFixed(3) : '—') + '</td>';
                        waveCells += '<td class="colAug colWave' + wi + ' col-aug" style="' + ws + '">' + wd.disch_poi_mwh.toFixed(3) + '</td>';
                    } else {
                        waveCells += '<td class="colAug colWave' + wi + ' col-aug" style="' + ws + '">—</td>';
                        waveCells += '<td class="colAug colWave' + wi + ' colDc col-aug" style="' + ws + (showDc ? '' : 'display:none;') + '">—</td>';
                        waveCells += '<td class="colAug colWave' + wi + ' colDcAux col-aug" style="' + ws + (showDcAux ? '' : 'display:none;') + '">—</td>';
                        waveCells += '<td class="colAug colWave' + wi + ' colMv col-aug" style="' + ws + (showMv ? '' : 'display:none;') + '">—</td>';
                        waveCells += '<td class="colAug colWave' + wi + ' col-aug" style="' + ws + '">—</td>';
                    }
                }

                // Cumulative columns: show existing + new installation separately in aug year
                var cumulEnergy = '—';
                var cumulPoi = '—';
                if (hasAug) {
                    // Check if a new wave starts this year — show "existing + new" format
                    var newWaveEnergy = 0;
                    var newWavePoi = 0;
                    for (var nwi = 1; nwi <= 3; nwi++) {
                        if (waveDetails && waveDetails[String(nwi)] && waveDetails[String(nwi)].start_year == yr) {
                            var nwd = waveDetails[String(nwi)].by_year[yr];
                            if (nwd) {
                                newWaveEnergy += nwd.energy_mwh;
                                newWavePoi += nwd.disch_poi_mwh;
                            }
                        }
                    }
                    if (newWaveEnergy > 0) {
                        var existingEnergy = d.total_energy_mwh - newWaveEnergy;
                        var existingPoi = d.dischargeable_energy_poi_mwh - newWavePoi;
                        cumulEnergy = existingEnergy.toFixed(1) + ' + ' + newWaveEnergy.toFixed(1);
                        cumulPoi = existingPoi.toFixed(1) + ' + ' + newWavePoi.toFixed(1);
                    } else {
                        cumulEnergy = d.total_energy_mwh.toFixed(3);
                        cumulPoi = d.dischargeable_energy_poi_mwh.toFixed(3);
                    }
                }

                rows += '<tr>' +
                    '<td class="col-year">' + yr + '</td>' +
                    '<td class="col-ret" data-level="' + retLevel + '">' + d.retention_pct.toFixed(1) + '%</td>' +
                    '<td class="col-num">' + d.total_energy_mwh.toFixed(3) + '</td>' +
                    '<td class="colDc col-num" style="' + dcStyle + '">' + (d.dischargeable_energy_dc_mwh != null ? d.dischargeable_energy_dc_mwh.toFixed(3) : '—') + '</td>' +
                    '<td class="colDcAux col-num" style="' + dcAuxStyle + '">' + (d.dischargeable_energy_dc_aux_mwh != null ? d.dischargeable_energy_dc_aux_mwh.toFixed(3) : '—') + '</td>' +
                    '<td class="colMv col-num" style="' + mvStyle + '">' + (d.dischargeable_energy_mv_mwh != null ? d.dischargeable_energy_mv_mwh.toFixed(3) : '—') + '</td>' +
                    '<td class="col-num">' + d.dischargeable_energy_poi_mwh.toFixed(3) + '</td>' +
                    '<td class="colThroughput col-num" style="' + throughputStyle + '">' + (Math.min(d.dischargeable_energy_poi_mwh, reqEnergy) * opDays).toFixed(0) + '</td>' +
                    waveCells +
                    '<td class="colAug col-aug-total" style="' + augStyle + ';color:#888;">' + cumulEnergy + '</td>' +
                    '<td class="colAug col-aug-highlight" style="' + augStyle + ';font-weight:700;color:var(--color-primary);font-size:13px;">' + cumulPoi + '</td>' +
                    '</tr>';
            });
            tbody.innerHTML = rows;
        }

        // Retention Chart — Dischargeable Energy @POI
        if (result.retention && result.retention.curve && window.BESSCharts) {
            var augMarkers = collectAugMarkers();
            var reqEnergyPoi = parseFloat(document.getElementById('requiredEnergyMwh') ?
                document.getElementById('requiredEnergyMwh').value : 0) || 0;
            BESSCharts.drawRetentionCurve('retentionChart', result.retention,
                reqEnergyPoi, augMarkers);
        }

        // ── SOC & Convergence Display ──
        var socRow = document.getElementById('socConvergenceRow');
        var socData = (result.convergence && result.convergence.soc) ? result.convergence.soc : result.soc;
        if (socRow && socData) {
            socRow.style.display = '';
            var soc = socData;
            setText('res-socHigh', (soc.soc_high * 100).toFixed(1));
            setText('res-socLow', (soc.soc_low * 100).toFixed(1));
            setText('res-socRest', (soc.soc_rest * 100).toFixed(1));
            setText('res-appliedDod', (soc.applied_dod * 100).toFixed(1));

            // SOC Bar visualization
            var lowPct = soc.soc_low * 100;
            var activePct = soc.applied_dod * 100;
            var highPct = (1 - soc.soc_high) * 100;
            var zoneLow = document.getElementById('socZoneLow');
            var zoneActive = document.getElementById('socZoneActive');
            var zoneHigh = document.getElementById('socZoneHigh');
            var markerRest = document.getElementById('socMarkerRest');
            if (zoneLow) zoneLow.style.width = lowPct + '%';
            if (zoneActive) zoneActive.style.width = activePct + '%';
            if (zoneHigh) zoneHigh.style.width = highPct + '%';
            if (markerRest) markerRest.style.left = (soc.soc_rest * 100) + '%';
            setText('socLabelLow', 'SOC Low: ' + lowPct.toFixed(0) + '%');
            setText('socLabelMid', 'Applied DoD: ' + activePct.toFixed(1) + '%');
            setText('socLabelHigh', 'SOC High: ' + (soc.soc_high * 100).toFixed(0) + '%');
        } else if (socRow) {
            socRow.style.display = 'none';
        }

        // Convergence info
        if (result.convergence) {
            var conv = result.convergence;
            var statusEl = document.getElementById('res-convStatus');
            if (statusEl) {
                statusEl.innerHTML = conv.converged
                    ? '<span class="badge badge--ok">CONVERGED</span>'
                    : '<span class="badge badge--danger">NOT CONVERGED</span>';
            }
            setText('res-convIterations', conv.iterations);
            setText('res-convDelta', conv.final_delta != null ? conv.final_delta.toExponential(2) : '—');
        }

        // Store result for session use
        try { sessionStorage.setItem('bess_last_result', JSON.stringify(result)); } catch (e) { /* noop */ }

        // Store params for RTE page
        try {
            var formSnap = collectFormData();
            sessionStorage.setItem('rte_params', JSON.stringify({
                efficiency: {
                    hv_ac_cabling: formSnap.hv_ac_cabling || 0.999,
                    hv_transformer: formSnap.hv_transformer || 0.995,
                    mv_ac_cabling: formSnap.mv_ac_cabling || 0.999,
                    mv_transformer: formSnap.mv_transformer || 0.993,
                    lv_cabling: formSnap.lv_cabling || 0.996,
                    pcs_efficiency: formSnap.pcs_efficiency || 0.985,
                    dc_cabling: formSnap.dc_cabling || 0.999,
                },
                power_flow: result.power_flow || {},
                rte: result.rte || {},
                summary: result.summary || {},
            }));
        } catch (e) { /* noop */ }
    }

    function collectAugMarkers() {
        var markers = [];
        var container = document.getElementById('augCompactWaves');
        if (container) {
            var chips = container.querySelectorAll('.aug-chip');
            for (var i = 0; i < chips.length; i++) {
                var inp = chips[i].querySelector('input[type="number"]');
                if (!inp) continue;
                var yr = parseInt(inp.value, 10);
                if (!isNaN(yr) && yr >= 1) markers.push({ year: yr, label: 'Wave ' + (i + 1) });
            }
        }
        return markers;
    }

    // ── Auto-Recommend Augmentation ──
    window.autoRecommendAugmentation = function () {
        // Build payload from lastResult if available, or from form inputs
        var data = collectFormData();
        var payload;

        if (lastResult && lastResult.battery && lastResult.efficiency) {
            var bat = lastResult.battery;
            var eff = lastResult.efficiency;
            payload = {
                cp_rate: bat.cp_rate,
                installation_energy_dc_mwh: bat.installation_energy_dc_mwh,
                project_life_yr: parseInt(data.project_life) || 20,
                product_type: data.battery_product_type,
                total_dc_to_aux_eff: eff.total_dc_to_aux_eff,
                required_energy_poi_mwh: parseFloat(data.required_energy_mwh),
                nameplate_energy_per_link_mwh: bat.nameplate_energy_per_link_mwh,
                links_per_pcs: lastResult.pcs.links_per_pcs || 2,
                annual_degradation_rate: 0.02,
                total_bat_poi_eff: eff.total_bat_poi_eff,
                total_battery_loss_factor: eff.total_battery_loss_factor,
                bat_to_mv_eff: lastResult.summary ? lastResult.summary.bat_to_mv_eff : 1.0,
                mv_to_poi_eff: lastResult.summary ? lastResult.summary.mv_to_poi_eff : 1.0,
                no_of_links: bat.no_of_links || 0,
                duration_hr: bat.duration_bol_hr || 0,
                aux_power_per_link_mw: bat.no_of_links > 0 ? (bat.aux_power_peak_mw / bat.no_of_links) : 0,
            };
        } else {
            // Pre-calculate mode: use form values with defaults
            var reqEnergy = parseFloat(data.required_energy_mwh);
            if (!reqEnergy || reqEnergy <= 0) {
                alert('Enter Required Energy (MWh) first.');
                return;
            }
            var estLinks = Math.ceil(reqEnergy * 1.15 / 5.554);
            payload = {
                cp_rate: 0.25,
                installation_energy_dc_mwh: reqEnergy * 1.15,
                project_life_yr: parseInt(data.project_life) || 20,
                product_type: data.battery_product_type || 'JF3 0.25 DC LINK',
                total_dc_to_aux_eff: 0.95,
                required_energy_poi_mwh: reqEnergy,
                nameplate_energy_per_link_mwh: 5.554,
                links_per_pcs: 2,
                annual_degradation_rate: 0.02,
                total_bat_poi_eff: 0.93,
                total_battery_loss_factor: 0.98,
                bat_to_mv_eff: 0.97,
                mv_to_poi_eff: 0.994,
                no_of_links: estLinks,
                duration_hr: parseFloat(data.duration_hours) || 4,
                aux_power_per_link_mw: 0.005,
            };
        }

        var btn1 = document.getElementById('autoAugBtn');
        var btn2 = document.getElementById('autoAugBtnInput');
        if (btn1) btn1.disabled = true;
        if (btn2) btn2.disabled = true;

        fetch('/api/augmentation/recommend', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
            .then(function (r) {
                if (!r.ok) return r.json().then(function (e) { throw new Error(e.error || 'Server error'); });
                return r.json();
            })
            .then(function (rec) {
                // Show result in both input panel and results panel
                var resultEls = [
                    document.getElementById('augRecommendResult'),
                    document.getElementById('augRecommendResultInput'),
                ];
                var html;

                if (!rec.waves || rec.waves.length === 0) {
                    html = '<strong>No augmentation needed.</strong> Energy stays above requirement throughout project life.';
                } else {
                    html = '<strong>' + rec.waves.length + ' wave(s) recommended:</strong>';
                    rec.waves.forEach(function (w, i) {
                        html += '<div class="aug-wave-item">' +
                            '<strong>Wave ' + (i + 1) + '</strong>: Year ' + w.year +
                            ' — +' + w.additional_links + ' LINKs (+' + w.additional_energy_mwh.toFixed(1) + ' MWh)' +
                            '</div>';
                    });
                    html += '<div style="margin-top:4px;color:var(--color-text-muted);font-size:11px;">Total: +' +
                        rec.total_additional_links + ' LINKs (+' + rec.total_additional_energy_mwh.toFixed(1) + ' MWh). Adjust LINKs with +/− buttons, then Calculate.</div>';
                }

                resultEls.forEach(function (el) {
                    if (el) { el.style.display = 'block'; el.innerHTML = html; }
                });

                // Populate augmentation chips from recommendation
                if (rec.waves && rec.waves.length > 0) {
                    // Clear existing chips
                    var container = document.getElementById('augCompactWaves');
                    if (container) container.innerHTML = '';
                    augChipId = 0;

                    rec.waves.forEach(function (w) {
                        addAugChip(w.year, w.additional_links, w.additional_energy_mwh);
                    });
                    updateAugAddBtn();
                }
            })
            .catch(function (err) {
                var resultEls = [
                    document.getElementById('augRecommendResult'),
                    document.getElementById('augRecommendResultInput'),
                ];
                resultEls.forEach(function (el) {
                    if (el) { el.style.display = 'block'; el.innerHTML = '<span style="color:var(--color-danger);">Error: ' + err.message + '</span>'; }
                });
            })
            .finally(function () {
                if (btn1) btn1.disabled = false;
                if (btn2) btn2.disabled = false;
            });
    };

    // Toggle retention table optional columns
    window.toggleRetCol = function (cls, show) {
        var cells = document.querySelectorAll('.' + cls);
        for (var i = 0; i < cells.length; i++) {
            cells[i].style.display = show ? '' : 'none';
        }
    };

    function setText(id, val) {
        var el = document.getElementById(id);
        if (el) el.textContent = val;
    }

    function setHtml(id, html) {
        var el = document.getElementById(id);
        if (el) el.innerHTML = html;
    }

    // ══════════════════════════════════════════════════════════
    // EXPORT EXCEL
    // ══════════════════════════════════════════════════════════
    window.exportToExcel = function () {
        if (!lastResult) {
            alert('Run a calculation first before exporting.');
            return;
        }
        fetch('/api/export', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ result: lastResult, inputs: collectFormData() }),
        })
            .then(function (r) {
                if (!r.ok) throw new Error('Export failed: ' + r.status);
                return r.blob();
            })
            .then(function (blob) {
                var url = URL.createObjectURL(blob);
                var a = document.createElement('a');
                a.href = url;
                a.download = 'SI_Sizing_Result.xlsx';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            })
            .catch(function (err) {
                showError('Export failed: ' + err.message);
            });
    };

    // ══════════════════════════════════════════════════════════
    // PROJECT SAVE / LOAD
    // ══════════════════════════════════════════════════════════
    window.saveProject = function () {
        var data = collectFormData();
        var name = data.project_title || ('Project_' + Date.now());

        setStatus('Saving...');

        fetch('/api/projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, inputs: data, result: lastResult }),
        })
            .then(function (r) {
                if (!r.ok) return r.json().then(function (e) { throw new Error(e.error || 'Save failed'); });
                return r.json();
            })
            .then(function (resp) {
                setStatus('Saved: ' + (resp.name || name) + ' (' + new Date().toLocaleTimeString() + ')');
            })
            .catch(function (err) {
                // Fallback: save to localStorage
                try {
                    var projects = JSON.parse(localStorage.getItem('bess_projects') || '{}');
                    projects[name] = { inputs: data, result: lastResult, saved_at: new Date().toISOString() };
                    localStorage.setItem('bess_projects', JSON.stringify(projects));
                    setStatus('Saved locally: ' + name);
                } catch (le) {
                    showError('Save failed: ' + err.message);
                }
            });
    };

    window.loadProject = function () {
        // Try server first
        fetch('/api/projects')
            .then(function (r) {
                if (!r.ok) throw new Error('Load failed');
                return r.json();
            })
            .then(function (list) {
                if (!list || list.length === 0) {
                    // Fallback to localStorage
                    loadFromLocalStorage();
                    return;
                }
                showProjectPicker(list);
            })
            .catch(function () {
                loadFromLocalStorage();
            });
    };

    function loadFromLocalStorage() {
        var projects;
        try {
            projects = JSON.parse(localStorage.getItem('bess_projects') || '{}');
        } catch (e) { projects = {}; }

        var keys = Object.keys(projects);
        if (keys.length === 0) {
            alert('No saved projects found.');
            return;
        }

        var list = keys.map(function (k) { return { id: k, name: k, inputs: projects[k].inputs, result: projects[k].result }; });
        showProjectPicker(list);
    }

    function showProjectPicker(list) {
        var names = list.map(function (p, i) { return (i + 1) + '. ' + p.name; }).join('\n');
        var choice = prompt('Select a project to load:\n\n' + names + '\n\nEnter number:');
        if (!choice) return;
        var idx = parseInt(choice, 10) - 1;
        if (isNaN(idx) || idx < 0 || idx >= list.length) {
            alert('Invalid selection.');
            return;
        }
        var project = list[idx];
        if (project.inputs) fillForm(project.inputs);
        if (project.result) {
            lastResult = project.result;
            displayResults(project.result);
        }
        setStatus('Loaded: ' + project.name);
    }

    function fillForm(inputs) {
        function setVal(id, v) {
            var el = document.getElementById(id);
            if (el && v !== undefined && v !== null) el.value = v;
        }

        setVal('projectTitle',          inputs.project_title);
        setVal('customer',              inputs.customer);
        setVal('projectLife',           inputs.project_life);
        setVal('poiLevel',              inputs.poi_level);
        setVal('voltageLevel',          inputs.voltage_level_kv);
        setVal('requiredPower',         inputs.required_power_mw);
        setVal('requiredEnergy',        inputs.required_energy_mwh);
        setVal('powerFactor',           inputs.power_factor);
        setVal('auxPowerSource',        inputs.aux_power_source);
        setVal('application',           inputs.application);
        setVal('temperature',           inputs.temperature_c);
        setVal('altitude',              inputs.altitude);
        setVal('hvAcCabling',           inputs.hv_ac_cabling);
        setVal('hvTransformer',         inputs.hv_transformer);
        setVal('mvAcCabling',           inputs.mv_ac_cabling);
        setVal('mvTransformer',         inputs.mv_transformer);
        setVal('lvCabling',             inputs.lv_cabling);
        setVal('pcsEfficiency',         inputs.pcs_efficiency);
        setVal('dcCabling',             inputs.dc_cabling);
        setVal('branchingPoint',        inputs.branching_point);
        setVal('auxTrLv',              inputs.aux_tr_lv);
        setVal('auxLineLv',            inputs.aux_line_lv);
        setVal('appliedDod',            inputs.applied_dod);
        setVal('lossFactors',           inputs.loss_factors);
        setVal('mbmsConsumption',       inputs.mbms_consumption);
        setVal('batteryProductType',    inputs.battery_product_type);
        // Restore cascading PCS: find model key from saved config name
        if (inputs.pcs_configuration && allPcsConfigs.length) {
            var matchCfg = allPcsConfigs.filter(function (c) { return c.id === inputs.pcs_configuration; })[0];
            if (matchCfg) {
                var mKey = matchCfg.manufacturer + '|' + matchCfg.model;
                setVal('pcsModel', mKey);
                var modelSel = document.getElementById('pcsModel');
                var cfgSel = document.getElementById('pcsConfiguration');
                if (modelSel && cfgSel) {
                    onPcsModelChange(modelSel, cfgSel);
                    setVal('pcsConfiguration', inputs.pcs_configuration);
                    onPcsConfigChange(cfgSel);
                }
            }
        }
        setVal('restSocType',           inputs.rest_soc);
        setVal('restSocValue',          inputs.rest_soc_value);
        setVal('cyclePerDay',           inputs.cycle_per_day);
        setVal('operationDaysPerYear',  inputs.operation_days_per_year);

        // Restore augmentation chips
        var augContainer = document.getElementById('augCompactWaves');
        if (augContainer) augContainer.innerHTML = '';
        augChipId = 0;
        if (inputs.augmentation && inputs.augmentation.length) {
            inputs.augmentation.forEach(function (a) {
                addAugChip(a.year);
            });
        }

        updateEfficiencyPreview();
    }

    // ══════════════════════════════════════════════════════════
    // UI HELPERS
    // ══════════════════════════════════════════════════════════
    function setLoading(on) {
        var overlay = document.getElementById('loadingOverlay');
        if (overlay) overlay.classList.toggle('visible', on);

        var btn = document.getElementById('calculateBtn');
        if (btn) {
            btn.disabled = on;
            btn.innerHTML = on
                ? '<span class="spinner"></span> Calculating...'
                : '&#9654; Calculate';
        }
    }

    function showError(msg) {
        var panel = document.getElementById('errorPanel');
        var msgEl = document.getElementById('errorMsg');
        if (panel) panel.classList.add('visible');
        if (msgEl) msgEl.textContent = msg;
        if (panel) panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function hideError() {
        var panel = document.getElementById('errorPanel');
        if (panel) panel.classList.remove('visible');
    }

    function setStatus(msg) {
        var el = document.getElementById('saveStatus');
        if (el) el.textContent = msg;
    }

    // ══════════════════════════════════════════════════════════
    // WINDOW RESIZE — redraw charts
    // ══════════════════════════════════════════════════════════
    // ══════════════════════════════════════════════════════════
    // TAB 4 — AUXILIARY LOAD DISPLAY
    // ══════════════════════════════════════════════════════════

    /**
     * Update the Auxiliary Load tab display based on current product selection
     * and (optionally) calculation results.
     */
    function updateAuxiliaryDisplay() {
        var batSel = document.getElementById('batteryProductType');
        var productName = batSel ? batSel.value : '';

        var auxProductNameEl = document.getElementById('auxProductName');
        var auxPeakEl    = document.getElementById('auxPeakKw');
        var auxStandbyEl = document.getElementById('auxStandbyKw');
        var auxSourceEl  = document.getElementById('auxSourceDisplay');
        var auxTotalSec  = document.getElementById('auxTotalSection');

        // Show current aux power source
        var auxSrcSel = document.getElementById('auxPowerSource');
        if (auxSourceEl && auxSrcSel) {
            auxSourceEl.textContent = auxSrcSel.value || '—';
        }

        if (!productName) {
            if (auxProductNameEl) auxProductNameEl.textContent = 'No product selected — select a battery product in Tab 3.';
            if (auxPeakEl)    auxPeakEl.textContent = '—';
            if (auxStandbyEl) auxStandbyEl.textContent = '—';
            if (auxTotalSec)  auxTotalSec.style.display = 'none';
            return;
        }

        // Fetch aux data from the products API
        fetch('/api/products')
            .then(function (r) { return r.ok ? r.json() : Promise.reject('HTTP ' + r.status); })
            .then(function (data) {
                // Find aux consumption for this product
                var auxData = null;
                if (data._aux_consumption && data._aux_consumption[productName]) {
                    auxData = data._aux_consumption[productName];
                }

                if (auxProductNameEl) {
                    auxProductNameEl.textContent = productName;
                }

                if (auxData) {
                    if (auxPeakEl)    auxPeakEl.textContent = auxData.peak_kw.toFixed(2);
                    if (auxStandbyEl) auxStandbyEl.textContent = auxData.standby_kw.toFixed(2);
                } else {
                    if (auxPeakEl)    auxPeakEl.textContent = 'N/A';
                    if (auxStandbyEl) auxStandbyEl.textContent = 'N/A';
                }

                // If we have calculation results, show system-level totals
                if (lastResult && lastResult.battery) {
                    var bat = lastResult.battery;
                    var numLinks = bat.no_of_links || 0;
                    var totalPeakKw = bat.aux_power_peak_mw ? bat.aux_power_peak_mw * 1000 : (auxData ? auxData.peak_kw * numLinks : 0);
                    var totalPeakMw = totalPeakKw / 1000;

                    if (auxTotalSec) auxTotalSec.style.display = '';
                    var linksEl = document.getElementById('auxNumLinks');
                    var totalKwEl = document.getElementById('auxTotalPeakKw');
                    var totalMwEl = document.getElementById('auxTotalPeakMw');
                    if (linksEl)   linksEl.textContent = numLinks;
                    if (totalKwEl) totalKwEl.textContent = totalPeakKw.toFixed(1);
                    if (totalMwEl) totalMwEl.textContent = totalPeakMw.toFixed(3);
                } else {
                    if (auxTotalSec) auxTotalSec.style.display = 'none';
                }
            })
            .catch(function () {
                if (auxProductNameEl) auxProductNameEl.textContent = productName + ' (aux data unavailable)';
            });
    }

    // Hook: update aux display when product changes or calculation completes
    var _origOnBatteryChange = onBatteryChange;
    var origBatSel = document.getElementById('batteryProductType');
    if (origBatSel) {
        origBatSel.addEventListener('change', function () {
            setTimeout(updateAuxiliaryDisplay, 200);
        });
    }
    var auxPowerSourceSel = document.getElementById('auxPowerSource');
    if (auxPowerSourceSel) {
        auxPowerSourceSel.addEventListener('change', updateAuxiliaryDisplay);
    }

    // ══════════════════════════════════════════════════════════
    // UPLOAD TO SHARED DB
    // ══════════════════════════════════════════════════════════
    window.showUploadModal = function () {
        if (!lastResult) {
            alert('No calculation results yet. Run Calculate first.');
            return;
        }
        var modal = document.getElementById('uploadModal');
        if (!modal) return;
        modal.style.display = 'flex';
        document.getElementById('uploadError').style.display = 'none';
        document.getElementById('uploadSuccess').style.display = 'none';
        // Pre-fill project name from input form
        var titleEl = document.getElementById('projectTitle');
        if (titleEl && titleEl.value) {
            document.getElementById('uploadProjectName').value = titleEl.value;
        }
    };

    window.hideUploadModal = function () {
        var modal = document.getElementById('uploadModal');
        if (modal) modal.style.display = 'none';
    };

    window.doUploadToSharedDB = function () {
        var projectName = document.getElementById('uploadProjectName').value.trim();
        if (!projectName) {
            var errDiv = document.getElementById('uploadError');
            errDiv.textContent = 'Project name is required';
            errDiv.style.display = 'block';
            return;
        }
        var btn = document.getElementById('uploadBtn');
        btn.disabled = true;
        btn.textContent = 'Uploading...';

        var payload = {
            project_name: projectName,
            description: document.getElementById('uploadDescription').value.trim(),
            input_data: collectFormData(),
            result_data: lastResult
        };

        fetch('/api/shared/designs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
        .then(function (res) {
            if (res.ok) {
                var s = document.getElementById('uploadSuccess');
                s.innerHTML = 'Uploaded! <a href="/shared/' + res.data.id + '" style="color:#16a34a;font-weight:600;">View in Shared DB &rarr;</a>';
                s.style.display = 'block';
                document.getElementById('uploadError').style.display = 'none';
            } else {
                var e = document.getElementById('uploadError');
                e.textContent = res.data.error || 'Upload failed';
                e.style.display = 'block';
                if (res.data.error === 'Login required') {
                    e.innerHTML = 'Login required. <a href="/auth/login" style="color:#dc2626;font-weight:600;">Login here</a>';
                }
            }
        })
        .catch(function () {
            var e = document.getElementById('uploadError');
            e.innerHTML = 'Network error. <a href="/auth/login" style="color:#dc2626;font-weight:600;">Are you logged in?</a>';
            e.style.display = 'block';
        })
        .finally(function () {
            btn.disabled = false;
            btn.textContent = 'Upload';
        });
    };

    var resizeTimer;
    window.addEventListener('resize', function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function () {
            if (lastResult && lastResult.retention && lastResult.retention.curve && window.BESSCharts) {
                BESSCharts.drawRetentionCurve(
                    'retentionChart',
                    lastResult.retention.curve,
                    lastResult.battery.installation_energy_dc_mwh,
                    collectAugMarkers()
                );
            }
        }, 200);
    });

    // ═══════════════════════════════════════════════════════════
    // F2+F5: SVG Single Line Diagram
    // ═══════════════════════════════════════════════════════════
    function drawSLD(pf) {
        var svg = document.getElementById('pfSldSvg');
        if (!svg) return;
        var tooltip = document.getElementById('pfSldTooltip');

        // Clear existing
        svg.innerHTML = '';

        var stages = pf.stages;
        if (!stages || stages.length === 0) return;

        // Build a lookup by stage name for easy access
        var byName = {};
        stages.forEach(function(s) { byName[s.name] = s; });

        // Fixed viewBox — smaller = elements appear larger relative to container
        var W = 600, H = 200;
        svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);

        var nodeY = 60;
        var nodeW = 52, nodeH = 34;
        var margin = 40;
        var spacing = (W - 2 * margin) / 6;  // 7 nodes, 6 gaps

        // Node positions (x centers) - dynamically spaced
        var nodes = [
            { key: 'PCS_OUTPUT', x: margin,              label: 'PCS',    color: '#eab308', symbol: 'inverter' },
            { key: 'LV_LINE',    x: margin + spacing,     label: 'LV',     color: '#f97316', symbol: 'cable' },
            { key: 'MVT',        x: margin + spacing * 2, label: 'MVT',    color: '#3b82f6', symbol: 'transformer' },
            { key: 'MV_BUS',     x: margin + spacing * 3, label: 'MV Bus', color: '#8b5cf6', symbol: 'bus' },
            { key: 'MV_LINE',    x: margin + spacing * 4, label: 'MV Ln',  color: '#6366f1', symbol: 'cable' },
            { key: 'MPT',        x: margin + spacing * 5, label: 'MPT',    color: '#3b82f6', symbol: 'transformer' },
            { key: 'POI',        x: margin + spacing * 6, label: 'POI',    color: '#10b981', symbol: 'grid' }
        ];

        // Helper: create SVG element
        function el(tag, attrs) {
            var e = document.createElementNS('http://www.w3.org/2000/svg', tag);
            for (var k in attrs) e.setAttribute(k, attrs[k]);
            return e;
        }

        // Arrowhead marker definition (must come before line that uses it)
        var defs = el('defs', {});
        var marker = el('marker', { id: 'arrowhead', markerWidth: '8', markerHeight: '6', refX: '8', refY: '3', orient: 'auto' });
        marker.appendChild(el('polygon', { points: '0 0, 8 3, 0 6', fill: '#cbd5e1' }));
        defs.appendChild(marker);
        svg.appendChild(defs);

        // Draw main connection line
        svg.appendChild(el('line', {
            x1: nodes[0].x, y1: nodeY + nodeH / 2,
            x2: nodes[nodes.length - 1].x, y2: nodeY + nodeH / 2,
            stroke: '#cbd5e1', 'stroke-width': '4'
        }));

        // Draw aux branch (from MV_BUS downward) — with tooltip
        var auxStage = byName['AUX_BRANCH'];
        var mvBusNode = nodes[3]; // MV_BUS
        if (auxStage && auxStage.p_loss_mw !== 0) {
            var auxG = el('g', { cursor: 'pointer' });
            auxG.appendChild(el('line', {
                x1: mvBusNode.x, y1: nodeY + nodeH / 2 + 22,
                x2: mvBusNode.x, y2: nodeY + nodeH / 2 + 75,
                stroke: '#f59e0b', 'stroke-width': '2.5', 'stroke-dasharray': '6,4'
            }));
            auxG.appendChild(el('rect', {
                x: mvBusNode.x - 32, y: nodeY + nodeH / 2 + 75,
                width: 64, height: 30, rx: 6,
                fill: '#fffbeb', stroke: '#f59e0b', 'stroke-width': '2'
            }));
            var auxText = el('text', {
                x: mvBusNode.x, y: nodeY + nodeH / 2 + 95,
                'text-anchor': 'middle', 'font-size': '13', 'font-weight': '700', fill: '#b45309'
            });
            auxText.textContent = 'AUX';
            auxG.appendChild(auxText);
            var auxLabel = el('text', {
                x: mvBusNode.x + 42, y: nodeY + nodeH / 2 + 92,
                'font-size': '12', 'font-weight': '600', fill: '#dc2626'
            });
            auxLabel.textContent = Math.abs(auxStage.p_loss_mw).toFixed(1) + ' MW';
            auxG.appendChild(auxLabel);
            // Tooltip for aux
            auxG.addEventListener('mouseenter', function(e) {
                if (!tooltip) return;
                tooltip.innerHTML = '<strong style="color:#f59e0b;">AUX (Auxiliary Load)</strong><br>'
                    + 'P consumed = ' + Math.abs(auxStage.p_loss_mw).toFixed(3) + ' MW<br>'
                    + 'P after aux = ' + auxStage.p_mw.toFixed(3) + ' MW<br>'
                    + 'Q = ' + auxStage.q_mvar.toFixed(3) + ' MVAr<br>'
                    + 'S = ' + auxStage.s_mva.toFixed(3) + ' MVA<br>'
                    + 'Branches from MV Bus (' + auxStage.voltage_kv.toFixed(1) + ' kV)';
                tooltip.style.display = 'block';
                var rect = document.getElementById('pfSldContainer').getBoundingClientRect();
                tooltip.style.left = (e.clientX - rect.left + 12) + 'px';
                tooltip.style.top = (e.clientY - rect.top - 10) + 'px';
            });
            auxG.addEventListener('mouseleave', function() { if (tooltip) tooltip.style.display = 'none'; });
            auxG.addEventListener('mousemove', function(e) {
                if (!tooltip) return;
                var rect = document.getElementById('pfSldContainer').getBoundingClientRect();
                tooltip.style.left = (e.clientX - rect.left + 12) + 'px';
                tooltip.style.top = (e.clientY - rect.top - 10) + 'px';
            });
            svg.appendChild(auxG);
        }

        // Draw each node
        nodes.forEach(function(node) {
            var stage = byName[node.key];
            if (!stage) return;

            var x = node.x, y = nodeY;
            var g = el('g', { 'data-stage': node.key, cursor: 'pointer' });

            if (node.symbol === 'transformer') {
                g.appendChild(el('circle', { cx: x - 10, cy: y + nodeH / 2, r: 18, fill: 'white', stroke: node.color, 'stroke-width': '2.5' }));
                g.appendChild(el('circle', { cx: x + 10, cy: y + nodeH / 2, r: 18, fill: 'white', stroke: node.color, 'stroke-width': '2.5' }));
            } else if (node.symbol === 'bus') {
                g.appendChild(el('rect', { x: x - 28, y: y + nodeH / 2 - 6, width: 56, height: 12, rx: 3, fill: node.color }));
            } else if (node.symbol === 'cable') {
                g.appendChild(el('line', { x1: x - 22, y1: y + nodeH / 2 - 3, x2: x + 22, y2: y + nodeH / 2 - 3, stroke: node.color, 'stroke-width': '3' }));
                g.appendChild(el('line', { x1: x - 22, y1: y + nodeH / 2 + 3, x2: x + 22, y2: y + nodeH / 2 + 3, stroke: node.color, 'stroke-width': '3' }));
            } else {
                g.appendChild(el('rect', { x: x - nodeW / 2, y: y, width: nodeW, height: nodeH, rx: 8, fill: 'white', stroke: node.color, 'stroke-width': '2.5' }));
                var sym = el('text', { x: x, y: y + nodeH / 2 + 5, 'text-anchor': 'middle', 'font-size': '16', 'font-weight': '800', fill: node.color });
                sym.textContent = node.label;
                g.appendChild(sym);
            }

            // Label below
            if (node.symbol === 'transformer' || node.symbol === 'cable' || node.symbol === 'bus') {
                var lb = el('text', { x: x, y: y + nodeH + 18, 'text-anchor': 'middle', 'font-size': '13', fill: '#64748b', 'font-weight': '600' });
                lb.textContent = node.label;
                g.appendChild(lb);
            }

            // P value above (blue, large)
            var pText = el('text', { x: x, y: y - 12, 'text-anchor': 'middle', 'font-size': '15', 'font-weight': '700', fill: '#2563eb' });
            pText.textContent = stage.p_mw.toFixed(1);
            g.appendChild(pText);

            // Loss below connection (red)
            if (stage.p_loss_mw > 0.001 && node.symbol !== 'bus') {
                var lossText = el('text', { x: x, y: y + nodeH + 34, 'text-anchor': 'middle', 'font-size': '12', fill: '#dc2626' });
                lossText.textContent = '-' + stage.p_loss_mw.toFixed(2);
                g.appendChild(lossText);
            }

            // Voltage label
            var vText = el('text', { x: x, y: y - 28, 'text-anchor': 'middle', 'font-size': '11', fill: '#94a3b8' });
            vText.textContent = stage.voltage_kv.toFixed(1) + 'kV';
            g.appendChild(vText);

            // Hover tooltip
            g.addEventListener('mouseenter', function(e) {
                if (!tooltip) return;
                tooltip.innerHTML = '<strong style="color:' + node.color + ';">' + node.label + ' (' + node.key + ')</strong><br>'
                    + 'P = ' + stage.p_mw.toFixed(3) + ' MW<br>'
                    + 'Q = ' + stage.q_mvar.toFixed(3) + ' MVAr<br>'
                    + 'S = ' + stage.s_mva.toFixed(3) + ' MVA<br>'
                    + 'I = ' + Math.round(stage.current_a).toLocaleString() + ' A<br>'
                    + 'PF = ' + stage.pf.toFixed(4) + '<br>'
                    + 'V = ' + stage.voltage_kv.toFixed(1) + ' kV'
                    + (stage.p_loss_mw > 0.001 ? '<br><span style="color:#f87171;">\u25B3P = -' + stage.p_loss_mw.toFixed(3) + ' MW</span>' : '')
                    + (Math.abs(stage.q_loss_mvar) > 0.001 ? '<br><span style="color:#f87171;">\u25B3Q = -' + stage.q_loss_mvar.toFixed(3) + ' MVAr</span>' : '');
                tooltip.style.display = 'block';
                var rect = document.getElementById('pfSldContainer').getBoundingClientRect();
                tooltip.style.left = (e.clientX - rect.left + 12) + 'px';
                tooltip.style.top = (e.clientY - rect.top - 10) + 'px';
            });
            g.addEventListener('mouseleave', function() {
                if (tooltip) tooltip.style.display = 'none';
            });
            g.addEventListener('mousemove', function(e) {
                if (!tooltip) return;
                var rect = document.getElementById('pfSldContainer').getBoundingClientRect();
                tooltip.style.left = (e.clientX - rect.left + 12) + 'px';
                tooltip.style.top = (e.clientY - rect.top - 10) + 'px';
            });

            svg.appendChild(g);
        });

        // Direction arrow at bottom
        // Direction arrow at TOP of diagram
        var arrowY = 18;
        svg.appendChild(el('line', { x1: margin, y1: arrowY, x2: W - margin, y2: arrowY, stroke: '#cbd5e1', 'stroke-width': '1.5', 'marker-end': 'url(#arrowhead)' }));
        var arrowLabel = el('text', { x: W / 2, y: arrowY - 5, 'text-anchor': 'middle', 'font-size': '11', fill: '#94a3b8' });
        arrowLabel.textContent = 'Power Flow \u2192 (Discharge)';
        svg.appendChild(arrowLabel);
    }

    // ═══════════════════════════════════════════════════════════
    // F2+F5: Loss Waterfall Chart
    // ═══════════════════════════════════════════════════════════
    function drawLossWaterfall(pf) {
        var container = document.getElementById('pfWaterfallContainer');
        if (!container) return;
        container.innerHTML = '';

        var stages = pf.stages || [];
        if (stages.length === 0) return;

        // Collect loss stages
        var items = [];
        var pcsP = 0;
        var poiP = 0;
        stages.forEach(function(s) {
            if (s.name === 'PCS_OUTPUT') { pcsP = s.p_mw; return; }
            if (s.name === 'POI') { poiP = s.p_mw; return; }
            if (s.name === 'MV_BUS') return; // aggregation only, no loss
            if (Math.abs(s.p_loss_mw) < 0.0001) return;
            items.push({ name: s.name, loss: Math.abs(s.p_loss_mw) });
        });

        var maxP = pcsP;
        if (maxP <= 0) return;

        // Build bars
        var html = '';

        function buildBar(label, value, max, color, isLoss) {
            var pct = (value / max * 100).toFixed(1);
            var textColor = isLoss ? '#dc2626' : '#059669';
            var prefix = isLoss ? '-' : '';
            return '<div style="display:flex;align-items:center;margin-bottom:3px;">'
                + '<div style="width:90px;text-align:right;padding-right:8px;font-size:10px;color:#64748b;white-space:nowrap;">' + label + '</div>'
                + '<div style="flex:1;background:#f1f5f9;border-radius:3px;height:16px;position:relative;">'
                + '<div style="width:' + pct + '%;background:' + color + ';height:100%;border-radius:3px;min-width:2px;opacity:' + (isLoss ? '0.7' : '0.85') + ';"></div>'
                + '</div>'
                + '<div style="width:65px;text-align:right;font-size:10px;font-weight:700;color:' + textColor + ';font-family:monospace;padding-left:6px;">' + prefix + value.toFixed(2) + '</div>'
                + '</div>';
        }

        // PCS bar (full width, green)
        html += buildBar('PCS Output', pcsP, maxP, '#10b981', false);

        // Loss bars (red, proportional)
        var lossLabels = {
            'LV_LINE': 'LV Busway', 'MVT': 'MVT (Step-up TR)',
            'AUX_BRANCH': 'Aux Load', 'MV_LINE': 'MV Collector', 'MPT': 'MPT (Main TR)'
        };
        items.forEach(function(item) {
            var label = lossLabels[item.name] || item.name;
            html += buildBar(label, item.loss, maxP, '#ef4444', true);
        });

        // POI bar (green)
        html += buildBar('POI Output', poiP, maxP, '#10b981', false);

        container.innerHTML = html;
    }

    // ═══════════════════════════════════════════════════════════
    // F2+F5: Reactive Power Tab Display
    // ═══════════════════════════════════════════════════════════
    function updateReactivePowerTab(result) {
        var pf = result.power_flow;

        // If no power_flow data, hide the new sections and use legacy fallback
        if (!pf || !pf.stages) {
            // Legacy fallback: use old reactive_power result if available
            var rp = result.reactive_power;
            if (!rp) return;

            var bat = result.battery || {};
            var pcs = result.pcs || {};
            var sum = result.summary || {};

            var bufPct = parseFloat(document.getElementById('rpBufferPct') ? document.getElementById('rpBufferPct').value : 5) || 5;
            var leadLag = document.getElementById('rpLeadLag') ? document.getElementById('rpLeadLag').value : 'lagging';

            var pPoi = sum.required_power_mw ? sum.required_power_mw * 1000 : 0;
            var sPoi = rp.total_apparent_power_poi_kva || 0;
            var qGrid = rp.grid_kvar || 0;
            var pfPoi = pPoi > 0 ? (pPoi / sPoi) : 0;
            var qSign = leadLag === 'leading' ? -1 : 1;

            // Populate hidden legacy IDs for backward compat
            setText('rp-poi-p', pPoi.toFixed(1));
            setText('rp-poi-q', (qGrid * qSign).toFixed(1));
            setText('rp-poi-s', sPoi.toFixed(1));
            setText('rp-poi-pf', pfPoi.toFixed(4));

            var pLossHv = rp.p_loss_hv_kw || 0;
            var pAux = bat.aux_power_peak_mw ? bat.aux_power_peak_mw * 1000 : 0;
            var pMv = pPoi + pLossHv + pAux;
            var qHv = rp.hv_tr_kvar || 0;
            var qMvTr = sPoi * 0.08;
            var qMv = qGrid + qHv + qMvTr;
            var sMv = Math.sqrt(pMv * pMv + qMv * qMv);
            var pfMv = rp.pf_at_mv || (pMv / sMv);

            setText('rp-mv-p', pMv.toFixed(1));
            setText('rp-mv-q', (qMv * qSign).toFixed(1));
            setText('rp-mv-s', sMv.toFixed(1));
            setText('rp-mv-pf', pfMv.toFixed(4));

            var sInv = rp.total_s_inverter_kva || 0;
            var pInv = sInv * pfMv;
            var qInv = Math.sqrt(Math.max(sInv * sInv - pInv * pInv, 0));

            setText('rp-inv-p', pInv.toFixed(1));
            setText('rp-inv-q', (qInv * qSign).toFixed(1));
            setText('rp-inv-s', sInv.toFixed(1));
            setText('rp-inv-pf', pfMv.toFixed(4));

            var sAvail = rp.available_s_total_kva || 0;
            var sReqBuf = sInv * (1 + bufPct / 100);
            var margin = sAvail > 0 ? ((sAvail - sReqBuf) / sAvail * 100) : 0;
            var sufficient = sAvail >= sReqBuf;

            setText('rp-req-s', sInv.toFixed(1));
            setText('rp-avail-s', sAvail.toFixed(1));
            setText('rp-margin', margin.toFixed(1));
            var suffEl = document.getElementById('rp-sufficient');
            if (suffEl) {
                suffEl.innerHTML = sufficient
                    ? '<span style="color:#16a34a;font-weight:700;">YES \u2713</span>'
                    : '<span style="color:#dc2626;font-weight:700;">NO \u2717</span>';
            }

            var llLabel = document.getElementById('rp-lead-lag-label');
            if (llLabel) llLabel.textContent = leadLag === 'leading' ? 'Leading (capacitive)' : 'Lagging (inductive)';
            return;
        }

        // ── New power_flow display ──

        // Show sections, hide placeholder
        ['pfSldSection', 'pfStagesSection', 'pfSummarySection', 'pfWaterfallSection'].forEach(function(id) {
            var el = document.getElementById(id);
            if (el) el.style.display = '';
        });
        var ph = document.getElementById('pfStagesPlaceholder');
        if (ph) ph.style.display = 'none';

        var leadLag = document.getElementById('rpLeadLag') ? document.getElementById('rpLeadLag').value : 'lagging';
        var qSign = leadLag === 'leading' ? -1 : 1;

        // --- Build stages table ---
        var tbody = document.getElementById('pfStagesBody');
        if (tbody) {
            var rows = '';
            var stageLabels = {
                'POI': 'Grid POI', 'MPT': 'Main Power TR (MPT)',
                'MV_LINE': 'MV Collector Line', 'AUX_BRANCH': 'Aux Branch',
                'MV_BUS': 'MV Bus', 'MVT': 'Step-up TR (MVT)',
                'LV_LINE': 'LV Busway', 'PCS_OUTPUT': 'PCS Output'
            };
            var stageColors = {
                'POI': '#10b981', 'MPT': '#3b82f6', 'MV_LINE': '#6366f1',
                'AUX_BRANCH': '#f59e0b', 'MV_BUS': '#8b5cf6', 'MVT': '#3b82f6',
                'LV_LINE': '#f97316', 'PCS_OUTPUT': '#eab308'
            };

            // Display in reverse order (POI at top, PCS at bottom)
            var stages = pf.stages.slice().reverse();
            stages.forEach(function(s) {
                var label = stageLabels[s.name] || s.name;
                var color = stageColors[s.name] || '#888';
                var isEndpoint = (s.name === 'POI' || s.name === 'PCS_OUTPUT');
                var hasLoss = s.p_loss_mw > 0.001 || Math.abs(s.q_loss_mvar) > 0.001;

                // Row style: endpoints get bold, slightly different bg
                var rowStyle = isEndpoint
                    ? 'font-weight:700;background:#f8fafc;'
                    : '';

                rows += '<tr style="' + rowStyle + '">'
                    + '<td style="padding:6px 12px;white-space:nowrap;"><span style="display:inline-block;width:4px;height:14px;background:' + color + ';border-radius:2px;margin-right:8px;vertical-align:middle;"></span>' + label + ' <span style="font-size:10px;color:#94a3b8;">' + s.voltage_kv.toFixed(1) + 'kV</span></td>'
                    + '<td style="text-align:right;padding:6px 8px;font-family:var(--font-mono);color:#2563eb;">' + s.p_mw.toFixed(2) + '</td>'
                    + '<td style="text-align:right;padding:6px 8px;font-family:var(--font-mono);color:#7c3aed;">' + (s.q_mvar * qSign).toFixed(2) + '</td>'
                    + '<td style="text-align:right;padding:6px 8px;font-family:var(--font-mono);">' + s.s_mva.toFixed(2) + '</td>'
                    + '<td style="text-align:right;padding:6px 8px;font-family:var(--font-mono);">' + s.pf.toFixed(3) + '</td>'
                    + '<td style="text-align:right;padding:6px 8px;font-family:var(--font-mono);">' + Math.round(s.current_a).toLocaleString() + '</td>'
                    + '<td style="text-align:right;padding:6px 8px;font-family:var(--font-mono);color:' + (hasLoss ? '#dc2626' : '#ccc') + ';">' + (hasLoss ? '-' + s.p_loss_mw.toFixed(3) : '\u2014') + '</td>'
                    + '<td style="text-align:right;padding:6px 8px;font-family:var(--font-mono);color:' + (Math.abs(s.q_loss_mvar) > 0.001 ? '#dc2626' : '#ccc') + ';">' + (Math.abs(s.q_loss_mvar) > 0.001 ? '-' + s.q_loss_mvar.toFixed(3) : '\u2014') + '</td>'
                    + '</tr>';
            });
            tbody.innerHTML = rows;
        }

        // --- Summary section ---
        setText('pf-sys-eff', pf.system_efficiency_pct.toFixed(1));
        setText('pf-total-p-loss', pf.total_p_loss_mw.toFixed(2));
        setText('pf-total-q-loss', pf.total_q_consumed_mvar.toFixed(2));
        setText('pf-aux-mv', pf.aux_power_at_mv_mw.toFixed(2));
        setText('pf-direction', pf.direction === 'discharge' ? 'Discharge' : 'Charge');
        setText('pf-mode', pf.calculation_mode === 'top_down' ? 'Top-down' : 'Bottom-up');
        setText('pf-cap-ratio', pf.capacity_ratio_pct.toFixed(1));
        var suffEl = document.getElementById('pf-sufficient');
        if (suffEl) {
            suffEl.innerHTML = pf.is_pcs_sufficient
                ? '<span style="color:#16a34a;font-weight:700;">\u2713 Sufficient</span>'
                : '<span style="color:#dc2626;font-weight:700;">\u2717 Insufficient</span>';
        }

        // Hidden reference points (for other pages)
        setText('pf-req-s', pf.total_s_required_mva.toFixed(2));
        setText('pf-avail-s', pf.available_s_total_mva.toFixed(2));
        setText('pf-ref-poi-p', pf.p_at_poi.toFixed(2));
        setText('pf-ref-poi-q', (pf.q_at_poi * qSign).toFixed(2));
        setText('pf-ref-poi-s', pf.s_at_poi.toFixed(2));
        setText('pf-ref-poi-pf', pf.pf_at_poi.toFixed(4));
        setText('pf-ref-mv-p', pf.p_at_mv.toFixed(2));
        setText('pf-ref-mv-q', (pf.q_at_mv * qSign).toFixed(2));
        setText('pf-ref-mv-s', pf.s_at_mv.toFixed(2));
        setText('pf-ref-mv-pf', pf.pf_at_mv.toFixed(4));
        setText('pf-ref-pcs-p', pf.p_at_pcs.toFixed(2));
        setText('pf-ref-pcs-q', (pf.q_at_pcs * qSign).toFixed(2));
        setText('pf-ref-pcs-s', pf.s_at_pcs.toFixed(2));
        var pfPcs = pf.p_at_pcs / pf.s_at_pcs;
        setText('pf-ref-pcs-pf', isNaN(pfPcs) ? '\u2014' : pfPcs.toFixed(4));

        // Backward compat rp-* IDs
        setText('rp-poi-p', (pf.p_at_poi * 1000).toFixed(1));
        setText('rp-poi-q', (pf.q_at_poi * qSign * 1000).toFixed(1));
        setText('rp-poi-s', (pf.s_at_poi * 1000).toFixed(1));
        setText('rp-poi-pf', pf.pf_at_poi.toFixed(4));
        setText('rp-mv-p', (pf.p_at_mv * 1000).toFixed(1));
        setText('rp-mv-q', (pf.q_at_mv * qSign * 1000).toFixed(1));
        setText('rp-mv-s', (pf.s_at_mv * 1000).toFixed(1));
        setText('rp-mv-pf', pf.pf_at_mv.toFixed(4));
        setText('rp-inv-p', (pf.p_at_pcs * 1000).toFixed(1));
        setText('rp-inv-q', (pf.q_at_pcs * qSign * 1000).toFixed(1));
        setText('rp-inv-s', (pf.s_at_pcs * 1000).toFixed(1));
        setText('rp-inv-pf', isNaN(pfPcs) ? '\u2014' : pfPcs.toFixed(4));
        setText('rp-req-s', (pf.total_s_required_mva * 1000).toFixed(1));
        setText('rp-avail-s', (pf.available_s_total_mva * 1000).toFixed(1));
        setText('rp-margin', pf.capacity_ratio_pct.toFixed(1));
        var oldSuf = document.getElementById('rp-sufficient');
        if (oldSuf) {
            oldSuf.innerHTML = pf.is_pcs_sufficient
                ? '<span style="color:#16a34a;font-weight:700;">YES \u2713</span>'
                : '<span style="color:#dc2626;font-weight:700;">NO \u2717</span>';
        }

        // Draw SLD and Waterfall
        drawSLD(pf);
        drawLossWaterfall(pf);
    }

    // ═══════════════════════════════════════════════════════════
    // F4: Definition Tooltips
    // ═══════════════════════════════════════════════════════════
    var _definitions = null;

    function initDefinitionTooltips() {
        fetch('/api/definitions')
            .then(function (r) { return r.ok ? r.json() : {}; })
            .then(function (defs) {
                _definitions = defs;
                attachTooltips();
            })
            .catch(function () { _definitions = {}; });
    }

    function attachTooltips() {
        if (!_definitions) return;
        // Map input name attributes and result element IDs to definition keys
        var nameMap = {
            'required_power_mw': 'required_power_mw',
            'required_energy_mwh': 'required_energy_mwh',
            'project_life': 'project_life',
            'power_factor': 'power_factor',
            'oversizing_year': 'oversizing_year',
            'link_override': 'link_override',
            'aux_power_source': 'aux_power_source',
            'dc_cabling': 'dc_cabling',
            'pcs_efficiency': 'pcs_efficiency',
            'lv_cabling': 'lv_cabling',
            'mv_transformer': 'mv_transformer',
            'mv_ac_cabling': 'mv_ac_cabling',
            'hv_transformer': 'hv_transformer',
            'hv_ac_cabling': 'hv_ac_cabling',
            'applied_dod': 'applied_dod',
            'loss_factors': 'loss_factors',
            'mbms_consumption': 'mbms_consumption',
            'branching_point': 'branching_point',
            'aux_tr_lv': 'aux_tr_lv',
            'aux_line_lv': 'aux_line_lv',
            'rest_soc_value': 'rest_soc',
            'cycle_per_day': 'cycle_per_day',
            'temperature_c': 'temperature_c',
        };
        // Attach to input labels
        Object.keys(nameMap).forEach(function (inputName) {
            var defKey = nameMap[inputName];
            var def = _definitions[defKey];
            if (!def) return;
            var inp = document.querySelector('[name="' + inputName + '"]');
            if (!inp) return;
            var label = inp.closest('.form-group');
            if (!label) return;
            var lbl = label.querySelector('label');
            if (!lbl || lbl.querySelector('.def-icon')) return;
            lbl.appendChild(createDefIcon(def));
        });

        // Attach to result elements
        var resMap = {
            'res-noPcs': 'no_of_pcs',
            'res-noLinks': 'no_of_links',
            'res-instEnergy': 'installation_energy_dc_mwh',
            'res-usableEnergy': 'dischargeable_energy_poi_mwh',
            'res-duration': 'duration_bol_hr',
            'res-detailLinks': 'no_of_links',
            'res-detailRacks': 'no_of_racks',
            'res-detailInstEnergy': 'installation_energy_dc_mwh',
            'res-detailUsableEnergy': 'dischargeable_energy_poi_mwh',
            'res-cpRate': 'cp_rate',
            'res-powerOversizing': 'power_oversizing',
            'res-energyOversizing': 'energy_oversizing',
            'res-effBatPoi': 'total_bat_poi_eff',
            'res-effBatLoss': 'total_battery_loss_factor',
            'res-effDcAux': 'total_dc_to_aux_eff',
            'res-effTotal': 'total_efficiency',
            'res-rte': 'system_rte',
            'res-linksPerPcs': 'links_per_pcs',
            'res-noMvt': 'no_of_mvt',
            'res-apparentPower': 'apparent_power',
            'res-gridKvar': 'grid_kvar',
            'res-socHigh': 'soc_high',
            'res-socLow': 'soc_low',
            'res-socRest': 'rest_soc',
        };
        Object.keys(resMap).forEach(function (elId) {
            var defKey = resMap[elId];
            var def = _definitions[defKey];
            if (!def) return;
            var el = document.getElementById(elId);
            if (!el) return;
            // Wrap in tooltip container if not already wrapped
            if (el.parentNode.classList && el.parentNode.classList.contains('res-tooltip-wrap')) return;
            var wrapper = document.createElement('span');
            wrapper.className = 'res-tooltip-wrap';
            el.parentNode.insertBefore(wrapper, el);
            wrapper.appendChild(el);
            wrapper.appendChild(createDefTooltip(def));
        });
    }

    function buildTooltipHtml(def) {
        return '<div class="def-tooltip__name">' + escHtml(def.name) +
            (def.unit ? '<span class="def-tooltip__unit">[' + escHtml(def.unit) + ']</span>' : '') +
            '</div>' +
            '<div class="def-tooltip__desc">' + escHtml(def.description) + '</div>' +
            '<div class="def-tooltip__formula">' + escHtml(def.formula) + '</div>';
    }

    function createDefIcon(def) {
        var icon = document.createElement('span');
        icon.className = 'def-icon';
        icon.textContent = '?';
        var tip = document.createElement('div');
        tip.className = 'def-tooltip';
        tip.innerHTML = buildTooltipHtml(def);
        icon.appendChild(tip);
        return icon;
    }

    function createDefTooltip(def) {
        var tip = document.createElement('div');
        tip.className = 'def-tooltip';
        tip.innerHTML = buildTooltipHtml(def);
        return tip;
    }

    function escHtml(s) {
        if (!s) return '';
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
    }

    // ═══════════════════════════════════════════════════════════
    // F6: Usage Pattern & Average SOC
    // ═══════════════════════════════════════════════════════════
    var usagePatternChart = null;

    function initUsagePattern() {
        // Sync cycle/day from main input
        var mainCycle = document.getElementById('cyclePerDay');
        var patternCycle = document.getElementById('cyclePerDayPattern');
        if (mainCycle && patternCycle) {
            patternCycle.value = mainCycle.value;
            mainCycle.addEventListener('change', function () {
                patternCycle.value = mainCycle.value;
            });
        }
        // Sync rest SOC from main input
        var mainRestSoc = document.getElementById('restSocValue');
        var patternRestSoc = document.getElementById('restSocPattern');
        if (mainRestSoc && patternRestSoc) {
            patternRestSoc.value = mainRestSoc.value;
            mainRestSoc.addEventListener('change', function () {
                patternRestSoc.value = mainRestSoc.value;
            });
        }
        // Auto-calculate on input change
        var inputs = ['socMin', 'socMax', 'chargeHr', 'dischargeHr', 'restSocPattern'];
        inputs.forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.addEventListener('change', function () { calcAvgSoc(); });
        });
    }

    window.calcAvgSoc = function () {
        var socMin = parseFloat(document.getElementById('socMin').value) || 0;
        var socMax = parseFloat(document.getElementById('socMax').value) || 100;
        var chargeHr = parseFloat(document.getElementById('chargeHr').value) || 4;
        var dischargeHr = parseFloat(document.getElementById('dischargeHr').value) || 4;
        var restSoc = parseFloat(document.getElementById('restSocPattern').value) || 30;

        var cycleMid = (socMin + socMax) / 2;
        var dutyHours = chargeHr + dischargeHr;
        var restHours = 24 - dutyHours;
        if (restHours < 0) restHours = 0;
        var avgSoc = (cycleMid * dutyHours + restSoc * restHours) / 24;

        setText('avgSocValue', avgSoc.toFixed(1));
        setText('avgSocMid', cycleMid.toFixed(1) + '%');
        setText('avgSocDuty', dutyHours.toFixed(1) + 'hr');
        setText('avgSocRest', restHours.toFixed(1) + 'hr');
        setText('avgSocRestVal', restSoc.toFixed(0) + '%');

        renderUsagePatternChart(socMin, socMax, chargeHr, dischargeHr, restSoc, avgSoc);
    };

    function renderUsagePatternChart(socMin, socMax, chargeHr, dischargeHr, restSoc, avgSoc) {
        var canvas = document.getElementById('usagePatternChart');
        if (!canvas || !window.Chart) return;

        // Build 24hr data points (0.5hr resolution)
        var labels = [];
        var data = [];
        var bgColors = [];
        var step = 0.5;
        for (var h = 0; h < 24; h += step) {
            labels.push(h.toFixed(1));
            if (h < chargeHr) {
                // Charging: ramp from socMin to socMax
                var chPct = h / chargeHr;
                data.push(socMin + (socMax - socMin) * chPct);
                bgColors.push('rgba(76, 175, 80, 0.6)');
            } else if (h < chargeHr + dischargeHr) {
                // Discharging: ramp from socMax to socMin
                var disPct = (h - chargeHr) / dischargeHr;
                data.push(socMax - (socMax - socMin) * disPct);
                bgColors.push('rgba(244, 67, 54, 0.6)');
            } else {
                // Rest
                data.push(restSoc);
                bgColors.push('rgba(158, 158, 158, 0.3)');
            }
        }

        if (usagePatternChart) { usagePatternChart.destroy(); }

        // Inline plugin for avg SOC line (no external chartjs-plugin-annotation needed)
        var avgSocLinePlugin = {
            id: 'avgSocLine',
            afterDraw: function (chart) {
                var yScale = chart.scales.y;
                var ctx = chart.ctx;
                var yPixel = yScale.getPixelForValue(avgSoc);
                ctx.save();
                ctx.beginPath();
                ctx.setLineDash([6, 3]);
                ctx.strokeStyle = '#FF9800';
                ctx.lineWidth = 2;
                ctx.moveTo(chart.chartArea.left, yPixel);
                ctx.lineTo(chart.chartArea.right, yPixel);
                ctx.stroke();
                // Label
                ctx.fillStyle = '#FF9800';
                ctx.font = '10px sans-serif';
                ctx.textAlign = 'right';
                ctx.fillText('Avg SOC: ' + avgSoc.toFixed(1) + '%', chart.chartArea.right - 4, yPixel - 4);
                ctx.restore();
            }
        };

        usagePatternChart = new Chart(canvas.getContext('2d'), {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'SOC (%)',
                    data: data,
                    backgroundColor: bgColors,
                    borderWidth: 0,
                    barPercentage: 1.0,
                    categoryPercentage: 1.0,
                }]
            },
            plugins: [avgSocLinePlugin],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: {
                        title: { display: true, text: 'Hour', font: { size: 11 } },
                        ticks: {
                            callback: function (val, idx) { return idx % 4 === 0 ? labels[idx] : ''; },
                            font: { size: 10 }
                        },
                        grid: { display: false }
                    },
                    y: {
                        min: 0, max: 100,
                        title: { display: true, text: 'SOC (%)', font: { size: 11 } },
                        ticks: { font: { size: 10 } }
                    }
                }
            }
        });
    }

}());
