function T = cg_auto_suite(level)
% CG_AUTO_SUITE  All tests of the complete CabinGuard-ADI simulation in one command.
%   cg_auto_suite('unit')   : chain without Simulink (Driver, Detector, Faults, Host, Gateway, Telem) - seconds
%   cg_auto_suite('quick')  : unit + 6 closed-loop runs in CabinGuardAuto (full model, detailed plant)
%   cg_auto_suite('full')   : unit + all closed-loop runs (about 20 runs; start it and leave it)
%   Closed loop = the whole chain: Driver incapacitated -> detector -> Host -> Gateway -> take-over -> perception, decision,
%   guidance, control -> detailed plant (Vehicle Dynamics Blockset wheels + brakes).  Each run is checked against what it must do.
%   Output: screen, results/suite_system.csv, results/suite_system.txt.  A FAIL line is a finding, not hidden.
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
if ~isfolder('results'), mkdir('results'); end
if nargin < 1, level = 'quick'; end
diary(fullfile('results', 'suite_system.txt'));  cleanupD = onCleanup(@() diary('off'));
fprintf('CabinGuard-ADI complete test suite, level "%s", %s\n', level, char(datetime('now')));
okU = cg_sys_unittest;
T = table();
if strcmp(level, 'unit')
    fprintf('\nSUITE: %s (unit level only)\n', ternary(okU, 'PASS', 'FAIL'));  return
end

base = struct('type', 'highway', 'seed', 1, 'T', 40, 'sys', 1, 't_on', 2, 'ev', 1, 'plot', true, 'quiet', true, 'accel', true, 'plant', 1);
if strcmp(level, 'github'), base = rmfield(base, 'T'); end
Cs = {};   % name, opts (override of base), check function name, quick?
Cs(end+1,:) = {'syncope',                      struct('ev', 1, 'plot', true),                         'takeover',  true};
Cs(end+1,:) = {'seizure',                      struct('ev', 2, 'plot', true),                         'takeover',  false};
Cs(end+1,:) = {'conscious driver (no event)',  struct('ev', 0),                                       'none',      true};
Cs(end+1,:) = {'false alarm, camera only',     struct('ev', 0, 'fa', [3 2 1]),                        'none',      false};
Cs(end+1,:) = {'long false alarm + driver brakes', struct('ev', 0, 'fa', [3 6 2], 't_can', 4.2),     'cancel',    true};
Cs(end+1,:) = {'camera lost',                  struct('fault', 1),                                    'takeover',  false};
Cs(end+1,:) = {'IMU lost',                     struct('fault', 2),                                    'takeover',  false};
Cs(end+1,:) = {'seat sensor lost',             struct('fault', 3),                                    'takeover',  false};
Cs(end+1,:) = {'host hangs after HAZARD',      struct('fault', 4, 't_fault', 8.2),                    'hang',      true};
Cs(end+1,:) = {'forged command',               struct('fault', 5),                                    'attack',    true};
Cs(end+1,:) = {'replayed command',             struct('fault', 6),                                    'attack',    false};
Cs(end+1,:) = {'valid MAC, implausible decel', struct('fault', 7),                                    'attack',    false};
Cs(end+1,:) = {'cellular down (e-call by SMS)', struct('fault', 8),                                   'sms',       true};
Cs(end+1,:) = {'camera blinded / spoofed',     struct('fault', 9),                                    'takeover',  false};
Cs(end+1,:) = {'valid MAC, phase skipped',     struct('fault', 11),                                   'early',     false};
Cs(end+1,:) = {'detector delay 0.5 s',         struct('det_delay', 0.5),                              'takeover',  false};
Cs(end+1,:) = {'detector delay 2.0 s',         struct('det_delay', 2.0),                              'takeover',  false};
Cs(end+1,:) = {'rural scene, syncope',         struct('type', 'rural', 'seed', 2, 'plot', true),      'takeover',  false};
Cs(end+1,:) = {'rural scene, take-over at ALERT', struct('type', 'rural', 'seed', 2, 'go_phase', 1, 'plot', true), 'takeover', false};
Cs(end+1,:) = {'city scene, syncope',          struct('type', 'city', 'seed', 4, 'plot', true),       'takeover',  false};
if strcmp(level, 'quick'), Cs = Cs([Cs{:,4}]', :); end
if strcmp(level, 'github')                         % same chain with the values of the Python system (see cg_auto_opts)
    Cs = Cs([1 2 3 6 13], :);
    for k = 1:size(Cs, 1), Cs{k, 2}.profile = 'github'; end
end
n = size(Cs, 1);
fprintf('\n=== Closed loop in CabinGuardAuto: %d runs (each a few minutes with the detailed plant) ===\n', n);
rows = {};  runs = cell(n, 1);
for k = 1:n
    o = base;  ov = Cs{k,2};  f = fieldnames(ov);  for q = 1:numel(f), o.(f{q}) = ov.(f{q}); end
    o = cg_auto_opts(o);                 % fills every option the run needs (fault, det_delay, brake_s ...)
    o.name = sprintf('suite%02d', k);
    t0 = tic;
    try
        r = cg_auto_run(o);  E = r.metrics;  I = r.sysinfo;
        runs{k} = struct('name', Cs{k,1}, 't', r.t, 'vx', r.vx, 'syslog', r.syslog(:, [1 2 3 4 7 9]), 'type', o.type);
        plotChain(r, Cs{k,1}, sprintf('results/suite%02d_chain.png', k));
        areqGo = NaN;  ig = find(r.t >= I.t_go & r.t <= I.t_go + 0.5);  if ~isempty(ig), areqGo = max(r.areq(ig)); end   % demand in the first 0.5 s after the take-over (the brake needs about 0.3 s to build up)
        [pass, why, unav] = verdict(Cs{k,3}, I, E, o, r.p.v0, areqGo);
        rows(end+1,:) = {Cs{k,1}, Cs{k,3}, o.fault, o.det_delay, I.t_alert, I.t_hazard, I.t_go, I.t_delivered, I.nrej, E.collision, E.pre_takeover, unav, areqGo, E.tstop, E.stopdist, E.min_gap, pass, why}; %#ok<AGROW>
    catch e
        pass = false;  why = ['run failed: ' strtok(e.message, newline)];
        rows(end+1,:) = {Cs{k,1}, Cs{k,3}, o.fault, o.det_delay, NaN, NaN, NaN, NaN, NaN, false, false, false, NaN, NaN, NaN, NaN, false, why}; %#ok<AGROW>
    end
    fprintf('%2d/%d  %-4s  %-36s  %s   [%.0f s]\n', k, n, ternary(pass, 'pass', 'FAIL'), Cs{k,1}, why, toc(t0));
end
T = cell2table(rows, 'VariableNames', {'case', 'expect', 'fault', 'det_delay_s', 't_alert_s', 't_hazard_s', 't_takeover_s', 't_ecall_delivered_s', 'rejected_frames', ...
    'collision', 'invalid_scene', 'unavoidable', 'areq_at_takeover', 'tstop_s', 'stopdist_m', 'min_gap_m', 'pass', 'note'});
writetable(T, fullfile('results', 'suite_system.csv'));
nf = sum(~T.pass);
try, plotOverview(T, runs); catch e, fprintf('  (overview picture failed: %s)\n', strtok(e.message, newline)); end
fprintf('\nCLOSED LOOP: %d runs, %d passed, %d FAILED\n', n, n - nf, nf);
fprintf('SUITE: %s\n', ternary(okU && nf == 0, 'ALL PASS', 'SOME FAIL - read the FAIL lines'));
end

function [pass, why, unav] = verdict(kind, I, E, o, v0, areqGo)
% what each case must do (design timing: take-over about onset + detector delay + 3 s + BRAKE time 4 s)
off = [3, 3 + o.alert_s, 3 + o.brake_s];     % ALERT, HAZARD, BRAKE after onset + detector delay (go_phase 1, 2, 3)
tgE = o.t_on + o.det_delay + off(min(max(o.go_phase, 1), 3));
% rule D.2: a collision is physically unavoidable when, at the take-over, the deceleration needed already exceeds what the car can do (about 8.5 m/s^2 plus ramp-up)
unav = E.collision && ~isnan(areqGo) && areqGo >= 8.0;
okScene = (~E.collision || unav) && ~E.pre_takeover;
why = '';
switch kind
    case 'takeover'
        tol = 0.7 + 0.6 * (o.fault == 1);
        pass = abs(I.t_go - tgE) <= tol + 0.1 * (o.fault == 1) && okScene && ~isnan(E.tstop);
        why = sprintf('take-over %.1f s (expected ~%.1f), stopped %s, %s', I.t_go, tgE, tx(E.tstop), sceneTxt(E));
    case 'none'
        % this test is about the chain staying quiet. A conscious driver would brake for the traffic; the model has no driver braking, so a
        % contact in the scene is reported but not counted against CabinGuard.
        pass = isnan(I.t_go) && isnan(I.t_alert);
        why = sprintf('no ALERT, no take-over (ALERT %s, take-over %s); scene: %s [model has no driver braking, not counted]', tx(I.t_alert), tx(I.t_go), sceneTxt(E));
    case 'cancel'
        pass = ~isnan(I.t_alert) && isnan(I.t_go) && okScene;
        why = sprintf('ALERT %s, cancelled, take-over %s, %s', tx(I.t_alert), tx(I.t_go), sceneTxt(E));
    case 'hang'
        pass = I.alive_lost && abs(I.t_go - tgE) <= 0.9 && okScene && ~isnan(E.tstop);
        why = sprintf('host lost %d, Gateway finished the stop, take-over %.1f s, %s', I.alive_lost, I.t_go, sceneTxt(E));
    case 'attack'
        pass = I.nrej > 100 && abs(I.t_go - tgE) <= 0.7 && okScene && ~isnan(E.tstop);
        why = sprintf('%d frames rejected, take-over %.1f s, %s', I.nrej, I.t_go, sceneTxt(E));
    case 'sms'
        pass = abs(I.t_delivered - I.t_ecall - 8) <= 0.5 && abs(I.t_go - tgE) <= 0.7 && okScene;
        why = sprintf('e-call placed %.1f s, delivered %.1f s, take-over %.1f s', I.t_ecall, I.t_delivered, I.t_go);
    case 'early'
        pass = I.nrej > 100 && I.t_go < tgE - 1 && okScene;
        why = sprintf('FINDING: accepted early, take-over %.1f s instead of %.1f s, %d frames rejected, %s', I.t_go, tgE, I.nrej, sceneTxt(E));
    otherwise
        pass = false;  why = 'unknown check';
end
if E.collision && ~strcmp(kind, 'none')
    if unav, why = [why sprintf(' - UNAVOIDABLE: %.1f m/s^2 were needed at the take-over, the car can do about 8.5 (reported separately)', areqGo)];
    else, why = [why sprintf(' - AVOIDABLE? only %.1f m/s^2 were needed at the take-over', areqGo)]; end
end
end

function s = sceneTxt(E)
if E.collision
    s = 'COLLISION';
    if isfield(E, 'hit_role') && ~isempty(E.hit_role)
        side = 'ahead';  if isfield(E, 'hit_rel') && numel(E.hit_rel) == 2 && E.hit_rel(1) < 0, side = 'BEHIND (rear-end hit)'; end
        s = sprintf('COLLISION with %s %s at %.1f s, impact %.1f m/s', E.hit_role, side, E.first_t, E.impact);
    end
elseif E.pre_takeover, s = 'invalid scene (contact before take-over)'; if isfield(E, 'pre_role'), s = sprintf('invalid scene (contact with %s at %.1f s, before take-over)', E.pre_role, E.pre_t); end; else, s = sprintf('no collision, gap %.1f m', E.min_gap); end
end
function s = tx(x)
if isnan(x), s = '-'; else, s = sprintf('%.1f s', x); end
end
function v = ternary(c, a, b)
if c, v = a; else, v = b; end
end

function plotChain(r, name, fn)
% timeline of the CabinGuard chain: Host state, Gateway phase, take-over, e-call, speed
try
    SL = r.syslog;  t = SL(:,1);
    f = figure('Visible', 'off', 'Position', [50 50 1100 650]);  tl = tiledlayout(f, 2, 1, 'TileSpacing', 'compact');
    nexttile;  hold on;
    stairs(t, SL(:,2), 'b', 'LineWidth', 1.5);  stairs(t, SL(:,3), 'r--', 'LineWidth', 1.2);
    stairs(t, 5 + SL(:,4), 'k', 'LineWidth', 1.2);  stairs(t, 7 + SL(:,6), 'm', 'LineWidth', 1.2);  stairs(t, 9 + SL(:,7), 'g', 'LineWidth', 1.2);
    yticks([0 1 2 3 4 5 6 7 8 9 10]);  grid on;  xlim([0 t(end)]);
    legend('Host state (0 normal, 1 ALERT, 2 HAZARD, 3 BRAKE, 4 STANDSTILL)', 'Gateway phase', 'take-over request (offset 5)', 'e-call placed (offset 7)', 'e-call delivered (offset 9)', 'Location', 'eastoutside');
    title('CabinGuard chain');  xlabel t;
    nexttile;  yyaxis left;  plot(r.t, r.vx, 'b', 'LineWidth', 1.5);  ylabel('speed (m/s)');
    yyaxis right;  plot(r.t, r.acmd, 'r');  ylabel('acceleration command (m/s^2)');  grid on;  xlim([0 t(end)]);  xlabel t;  title('Car');
    title(tl, sprintf('%s  |  rejected frames: %d', name, max(SL(:,9))));
    exportgraphics(f, fn, 'Resolution', 110);  close(f);  fprintf('  figure: %s\n', fn);
catch e
    fprintf('  (chain picture failed: %s)\n', strtok(e.message, newline));
end
end

function plotOverview(T, runs)
% one picture with all cases: speed, take-over time, e-call delivery, rejected frames
n = numel(runs);  f = figure('Visible', 'off', 'Position', [50 50 1500 900]);  tl = tiledlayout(f, 2, 2, 'TileSpacing', 'compact');
nexttile;  hold on;
for k = 1:n
    if ~isempty(runs{k}) && strcmp(runs{k}.type, 'highway'), plot(runs{k}.t, runs{k}.vx, 'LineWidth', 1); end
end
grid on;  xlabel t;  ylabel('speed (m/s)');  title('Highway scene: speed in every case (curves that never brake = no take-over)');
nexttile;  barh(T.t_takeover_s);  set(gca, 'YTick', 1:n, 'YTickLabel', T.case, 'YDir', 'reverse');  grid on;  xlabel('take-over time (s)');  title('Take-over time (missing bar = no take-over)');
nexttile;  barh(T.t_ecall_delivered_s);  set(gca, 'YTick', 1:n, 'YTickLabel', T.case, 'YDir', 'reverse');  grid on;  xlabel('e-call delivered (s)');  title('Emergency message delivery');
nexttile;  barh(T.rejected_frames);  set(gca, 'YTick', 1:n, 'YTickLabel', T.case, 'YDir', 'reverse');  grid on;  xlabel('frames rejected by the Gateway');  title('Gateway rejections');
title(tl, 'CabinGuard-ADI: all test cases');
exportgraphics(f, fullfile('results', 'suite_overview.png'), 'Resolution', 110);  close(f);  fprintf('  figure: results/suite_overview.png\n');
end
