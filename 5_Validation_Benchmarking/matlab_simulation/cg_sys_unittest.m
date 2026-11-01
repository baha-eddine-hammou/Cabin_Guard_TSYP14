function ok = cg_sys_unittest(verbose)
% CG_SYS_UNITTEST  Tests the CabinGuard chain WITHOUT Simulink (a few seconds):
%   Detector (surrogate of the AI) -> Faults -> Host -> Gateway -> Telem, with the Driver (syncope / seizure / conscious).
%   The car is a point mass here (it brakes with the Gateway's a_mrm once the Gateway has accepted the BRAKE phase).
%   Returns true when every check passes.  cg_sys_unittest;   or   cg_sys_unittest(true) for all details.
%   Expected values: design values of the model (verification 2 s, ALERT 2 s, ALERT-to-BRAKE 4 s, detector delay 1 s, MRM -3 m/s^2).
here = fileparts(mfilename('fullpath'));  addpath(here);
if nargin < 1, verbose = false; end
rows = {};  nfail = 0;
fprintf('\n=== CabinGuard chain: unit tests (no Simulink) ===\n');

% --- 1 normal take-over ---------------------------------------------------------------------------
for ev = 1:2
    R = chain(struct('ev', ev));
    nm = {'syncope', 'seizure'};  nm = nm{ev};
    chk(sprintf('%s: ALERT at ~6 s', nm), near(R.t_alert, 6.0, 0.4), sprintf('%.2f s', R.t_alert));
    chk(sprintf('%s: HAZARD 2 s after ALERT', nm), near(R.t_haz - R.t_alert, 2.0, 0.2), sprintf('%.2f s', R.t_haz - R.t_alert));
    chk(sprintf('%s: take-over (Gateway accepted BRAKE) at ~10 s', nm), near(R.t_go, 10.0, 0.4), sprintf('%.2f s', R.t_go));
    chk(sprintf('%s: car stops, max decel 3 m/s^2, parked', nm), R.v_end < 0.1 && near(-R.a_min, 3.0, 0.05) && R.parked, sprintf('v_end %.2f, a_min %.2f', R.v_end, R.a_min));
    chk(sprintf('%s: no frame rejected, e-call delivered at HAZARD', nm), R.nrej == 0 && near(R.t_deliv, R.t_haz, 0.2), sprintf('nrej %d, delivered %.2f s', R.nrej, R.t_deliv));
end

% --- 2 conscious driver and false alarms: the car must NOT take over ---------------------------------------------------------------
R = chain(struct('ev', 0));
chk('conscious driver: never takes over', isnan(R.t_go) && isnan(R.t_alert) && R.v_end > 24.9, sprintf('t_go %s', tx(R.t_go)));
R = chain(struct('ev', 0, 'fa', [3 2 1]));
chk('false alarm, camera only (wheel shows a steering driver): ignored (interlock + two-sensor rule)', isnan(R.t_go) && isnan(R.t_alert), sprintf('alert %s', tx(R.t_alert)));
R = chain(struct('ev', 0, 'fa', [3 2 2]));
chk('false alarm, all branches, 2 s: no take-over', isnan(R.t_go), sprintf('alert %s', tx(R.t_alert)));
R = chain(struct('ev', 0, 'fa', [3 6 2], 't_can', 4.2));
chk('long false alarm: ALERT is raised, conscious driver brakes -> CANCELLED, no take-over', ~isnan(R.t_alert) && isnan(R.t_go) && R.v_end > 24.9, sprintf('alert %s, go %s', tx(R.t_alert), tx(R.t_go)));

% --- 3 sensor losses: degraded modes, still brakes (a little later), mode reported ---------------------------------------
Rf = [1 2 3];  mdE = [1 2 4];  tgE = [10.6 10.1 10.1];  sn = {'camera', 'IMU', 'seat sensor'};
for k = 1:3
    R = chain(struct('fault', Rf(k)));
    chk(sprintf('fault %d (%s lost): still takes over, degraded mode %d', Rf(k), sn{k}, mdE(k)), near(R.t_go, tgE(k), 0.4) && R.dmode == mdE(k) && R.v_end < 0.1, sprintf('go %s, dmode %d', tx(R.t_go), R.dmode));
end

% --- 4 attacks on the command boundary ------------------------------------------------------------
Rf = [5 6 7];  txt = {'forged command (bad MAC)', 'replayed command (stale freshness)', 'valid MAC, implausible decel -6 m/s^2'};
for k = 1:3
    R = chain(struct('fault', Rf(k)));
    chk(sprintf('fault %d %s: rejected, manoeuvre unchanged', Rf(k), txt{k}), R.nrej > 100 && near(R.t_go, 10.0, 0.4) && near(-R.a_min, 3.0, 0.05), sprintf('rejected %d, go %s, a_min %.2f', R.nrej, tx(R.t_go), R.a_min));
end
R = chain(struct('fault', 11));
chk('fault 11 valid MAC, phase skipped: out-of-order frames rejected; FINDING: the next phase is accepted early (brake ~2 s earlier, still limited to -3 m/s^2)', R.nrej > 100 && R.t_go < 9.0 && near(-R.a_min, 3.0, 0.05), sprintf('rejected %d, go %s', R.nrej, tx(R.t_go)));
R = chain(struct('fault', 9));
chk('fault 9 camera blinded (spoofed evidence): take-over unchanged (other sensors agree)', near(R.t_go, 10.0, 0.4), sprintf('go %s', tx(R.t_go)));

% --- 5 Host hang ----------------------------------------------------------------------------------
R = chain(struct('fault', 4, 't_fault', 8.2));
chk('fault 4 host hangs AFTER HAZARD: Gateway completes the stop alone (alive timeout 300 ms)', R.alive_lost && R.gwp == 3 && R.v_end < 0.1, sprintf('gwp %d, v_end %.2f', R.gwp, R.v_end));
R = chain(struct('fault', 4, 't_fault', 7.9));
chk('fault 4 host hangs BEFORE HAZARD: nothing is actuated (KNOWN LIMIT: no stop; the driver is still unresponsive)', R.alive_lost && R.v_end > 24.9, sprintf('gwp %d, v_end %.2f', R.gwp, R.v_end));

% --- 6 emergency call transport -----------------------------------------------------------------------
R = chain(struct('ev', 1, 'fault', 8, 'T', 100));
chk('fault 8 cellular down: e-call delivered by SMS about 8 s after it was placed', near(R.t_deliv - R.t_ecall, 8.0, 0.3), sprintf('%.2f s', R.t_deliv - R.t_ecall));
% --- 1b timeline of the Python system (profile 'github': latency 12 s, HAZARD +4 s, BRAKE +10 s after the verified event) ---
R = chain(struct('ev', 1, 'ddel', 9.0, 'alert_s', 4, 'brake_s', 10, 'v0', 27.8, 'T', 60));
chk('github profile: ALERT 14 s (onset 2 + latency 12), HAZARD +4 s, take-over +10 s', near(R.t_alert, 14.0, 0.4) && near(R.t_haz - R.t_alert, 4.0, 0.2) && near(R.t_go - R.t_alert, 10.0, 0.3) && R.v_end < 0.1, sprintf('alert %.2f, haz %.2f, go %.2f s, v_end %.2f', R.t_alert, R.t_haz, R.t_go, R.v_end));

R = chain(struct('ev', 1, 'fault', 10, 'T', 100));
chk('fault 10 all bearers down 60 s: not delivered before they return, delivered by the 30 s retry afterwards (the manoeuvre does not wait)', R.t_deliv > 62 && R.t_deliv < 80 && R.v_end < 0.1, sprintf('delivered %.1f s', R.t_deliv));

% --- 7 timing sweep: the detector delay moves the take-over one to one -----------------------------------------------------
tg = zeros(1, 3);  dd = [0.5 1 2];
for k = 1:3, R = chain(struct('ddel', dd(k)));  tg(k) = R.t_go; end
chk('detector delay 0.5 / 1 / 2 s moves the take-over by the same amount', near(tg(2) - tg(1), 0.5, 0.2) && near(tg(3) - tg(2), 1.0, 0.2), sprintf('go %.1f / %.1f / %.1f s', tg));

nt = size(rows, 1);  nfail = sum(~[rows{:, 2}]);
fprintf('\n%d checks, %d passed, %d FAILED\n', nt, nt - nfail, nfail);
ok = (nfail == 0);
if ok, fprintf('CHAIN: ALL CHECKS PASSED\n'); else, fprintf('CHAIN: SOME CHECKS FAILED (see lines marked FAIL)\n'); end

    function chk(name, cond, detail)
        cond = logical(cond);
        rows(end+1, :) = {name, cond, detail}; %#ok<AGROW>
        if cond && ~verbose, fprintf('  pass  %s\n', name);
        elseif cond, fprintf('  pass  %s   [%s]\n', name, detail);
        else, fprintf('  FAIL  %s   [%s]\n', name, detail); end
    end
end

function b = near(x, ref, tol)
b = ~isnan(x) && abs(x - ref) <= tol;
end

function s = tx(x)
if isnan(x), s = '-'; else, s = sprintf('%.2f s', x); end
end

function R = chain(o)
% closed loop of the chain at 10 ms with a point-mass car
d = struct('ev', 1, 't_on', 2, 'fault', 0, 't_fault', 2, 't_can', 0, 'fa', [0 0 0], 'ddel', 1.0, 'v0', 25, 'T', 40, 'alert_s', 2, 'brake_s', 4);
f = fieldnames(d);  for k = 1:numel(f), if ~isfield(o, f{k}), o.(f{k}) = d.(f{k}); end, end
pv = [o.t_on; o.ev; o.v0; 0; 1; o.brake_s; -3; o.fault; o.t_fault; o.t_can; 2; 0; o.alert_s; 2; 1];
dp = [o.ddel; 1; o.fa(1); o.fa(2); o.fa(3)];
clear cg_sys_host cg_sys_gateway cg_sys_telem
v = o.v0;  nrej = 0;  a_min = 0;  dm = 0;
R = struct('t_alert', NaN, 't_haz', NaN, 't_brake', NaN, 't_go', NaN, 't_deliv', NaN, 't_ecall', NaN);
parked = false;  alive_lost = false;  gwp = 0;
for i = 0:round(o.T / 0.01)
    t = i * 0.01;
    lam = cg_sys_detector(t, pv, dp);
    [lam_f, avail, att, cell_up, sms_up] = cg_sys_faults(t, lam, pv);
    [~, ~, tau, pedal, clonic, grip] = cg_sys_driver(t, 0, 0, v, pv);
    [hf, ~, ~, dmode, Pmax, cls, ecall, ~, st] = cg_sys_host(t, lam_f, avail, tau, grip, clonic, pedal, v, pv);
    [a_mrm, gwp, ~, ~, park, alive_lost, ~, nrej] = cg_sys_gateway(t, hf, att, v, pv);
    dlv = cg_sys_telem(t, ecall, cls, Pmax, cell_up, sms_up);
    dm = max(dm, dmode);
    if st >= 1 && isnan(R.t_alert), R.t_alert = t; end
    if st >= 2 && isnan(R.t_haz), R.t_haz = t; end
    if st >= 3 && isnan(R.t_brake), R.t_brake = t; end
    if gwp >= 3 && isnan(R.t_go), R.t_go = t; end
    if ecall > 0.5 && isnan(R.t_ecall), R.t_ecall = t; end
    if dlv > 0.5 && isnan(R.t_deliv), R.t_deliv = t; end
    if gwp >= 3, v = max(0, v + a_mrm * 0.01); end
    a_min = min(a_min, a_mrm);
    parked = park > 0.5;
end
R.v_end = v;  R.nrej = nrej;  R.a_min = a_min;  R.dmode = dm;  R.parked = parked;  R.alive_lost = logical(alive_lost);  R.gwp = gwp;
end
