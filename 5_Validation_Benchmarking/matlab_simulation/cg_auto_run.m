function res = cg_auto_run(o)
% CG_AUTO_RUN  One autonomous take-over: the driver stops responding at t_act, the car does the rest from its own sensors.
%   cg_auto_run                                              % highway scene 1
%   cg_auto_run(struct('type','city','seed',4))              % generated city scene with pedestrians / parked cars
%   cg_auto_run(struct('file','myRoad'))                     % YOUR scenario exported from the Driving Scenario Designer
%   cg_auto_run(struct('type','rural','seed',2,'mode','brake_only'))   % same scene, but the car never leaves its lane
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
if ~isfolder('results'), mkdir('results'); end
if nargin < 1, o = struct(); end
o = cg_auto_opts(o);
if o.sys ~= 0     % chain mode: the scene's hazards must be timed for the take-over the chain will request, not for the default t_act
    offs = [3, 3 + o.alert_s, 3 + o.brake_s];                   % ALERT, HAZARD, BRAKE after the onset + detector delay
    o.t_act = o.t_on + o.det_delay + offs(min(max(o.go_phase, 1), 3));
end
m = 'CabinGuardAuto';
if ~isfile(fullfile(here, [m '.slx'])), cg_auto_build(m); end
if ~bdIsLoaded(m), load_system(fullfile(here, m)); end
try, set_param(m, 'FastRestart', 'off'); catch, end
try, set_param(m, 'BusObjectLabelMismatch', 'none'); catch, end   % harmless bus element-name warnings
cg_dsd_bus();
cg_auto_defaults(true);          % all model constants back to the design values (a cleared workspace or an edited value cannot break the run)
if ~isempty(o.file)
    [sc, info, mk] = cg_auto_load(o.file, o);
else
    [sc, info] = cg_auto_scene(o);  mk = @() cg_auto_scene(o);
end
if isempty(o.T), o.T = info.T; end
try, sc.StopTime = o.T; catch, end
p = cg_auto_prep(sc, info.egoID, o, info);
signs = getSigns(o);
clear_eff = p.clear;  if strcmp(o.mode, 'brake_only'), clear_eff = 0; end
vars = {'ca_scn', sc; 'ca_ego_id', info.egoID; 'ca_v0', p.v0; 'ca_psi0', p.psi0; 'ca_X0', p.x0; 'ca_Y0', p.y0; 'ca_t_act', o.t_act; ...
        'ca_a_comf', o.a_comf; 'ca_clear', clear_eff; 'ca_wn', o.wn; 'ca_lka_in', signs(1); 'ca_lka_out', signs(2); 'ca_lw0', p.lw0};
for k = 1:size(vars, 1), assignin('base', vars{k,1}, vars{k,2}); end
% CabinGuard layer parameters (pv layout: see cg_sys_*.m) - design values, see CabinGuard_final_work.md
ev_eff = o.ev * (o.sys ~= 0);
pv = [o.t_on; ev_eff; p.v0; 0; 1; o.brake_s; o.mrm_decel; o.fault; o.t_fault; o.t_can; 2; 0; o.alert_s; o.tonic_s; o.host_on];
assignin('base', 'ca_pv', pv);  assignin('base', 'ca_sys', double(o.sys ~= 0));  assignin('base', 'ca_go_phase', o.go_phase);
assignin('base', 'ca_det', [o.det_delay; 1; o.fa(1); o.fa(2); o.fa(3)]);
if ~isempty(o.plant), assignin('base', 'ca_plant', o.plant);
elseif ~evalin('base', 'exist(''ca_plant'',''var'')'), assignin('base', 'ca_plant', 1); end
plantTxt = {'simple plant', 'detailed plant (Vehicle Dynamics Blockset)'};  plantTxt = plantTxt{1 + (evalin('base', 'ca_plant') ~= 0)};
set_param(m, 'StopTime', num2str(o.T));
% the Scenario Reader checks the ego ActorID against its own parameter: make it follow the scenario's ego
srb = [m '/SR'];  done = false;
try
    set_param(srb, 'ScenarioSource', 'From workspace');  set_param(srb, 'ScenarioVariableName', 'ca_scn');   % in case the block was pointed at a file
catch eSR
    fprintf('\n[warn] could not reset the Scenario Reader to the workspace scenario: %s\n       Close the model (bdclose all) and run cg_auto_build.\n', strtok(eSR.message, newline));
end
try, fprintf('    Scenario Reader: source = %s, variable = %s\n', get_param(srb, 'ScenarioSource'), get_param(srb, 'ScenarioVariableName')); catch, end
try
    dp = get_param(srb, 'DialogParameters');  fn = fieldnames(dp);
    for k = 1:numel(fn)
        pr = dp.(fn{k}).Prompt;
        if ~isempty(strfind(lower(pr), 'actorid')) && ~isempty(strfind(lower(pr), 'ego'))
            set_param(srb, fn{k}, num2str(info.egoID));  done = true;  break
        end
    end
catch, end
if ~done
    for nm = {'EgoVehicleActorID', 'EgoActorID', 'EgoVehicleID'}
        try, set_param(srb, nm{1}, num2str(info.egoID)); done = true; break, catch, end
    end
end
if ~o.quiet && info.egoID ~= 1, fprintf('    ego car of the scenario = actor %d%s\n', info.egoID, ternary(done, '', ' (could not set the Scenario Reader ID!)')); end
if o.accel, try, set_param(m, 'SimulationMode', 'accelerator'); catch, end
else, set_param(m, 'SimulationMode', 'normal'); end
if ~o.quiet
    fprintf('\n=== %s\n', info.title);
    for k = 1:numel(info.desc), fprintf('    - %s\n', info.desc{k}); end
    fprintf('    start %.1f m/s, driver unresponsive at t = %.1f s, road to the right %.1f m (%s), mode: %s, %s\n', p.v0, o.t_act, p.clear, p.clear_src, o.mode, plantTxt);
end
tic;  out = sim(m);  tsim = toc;
A = out.calog;
t = (0:size(A, 1) - 1)' * 0.02;
crashed = t(end) < o.T - 0.1;
X = A(:,1); Y = A(:,2); psi = A(:,3); vx = A(:,4); delta = A(:,7);
res = struct('t', t, 'X', X, 'Y', Y, 'psi', psi, 'vx', vx, 'delta', delta, 'e1', A(:,8), 'd', A(:,9), 'yref', A(:,10), 'vref', A(:,11), 'aref', A(:,12), ...
             'adem', A(:,14), 'areq', A(:,15), 'occ', A(:,16), 'commit', A(:,17), 'yshT', A(:,18), 'acmd', A(:,19), 'dcmd', A(:,20), ...
             'crashed', crashed, 'info', info, 'p', p, 'o', o);
if crashed
    res.crash_msg = sprintf('guard stopped the run at t = %.2f s: a controller command became NaN', t(end));
    if ~o.quiet, fprintf('\n*** %s\n', res.crash_msg); end
else
    res.crash_msg = '';
end
sysinfo = [];
if isprop(out, 'syslog') || isfield(out, 'syslog') || any(strcmp(out.who, 'syslog'))
    SL = out.syslog;  sysinfo = sysTimeline(SL, o);
    res.syslog = SL;  res.sysinfo = sysinfo;
    if o.sys ~= 0
        if isnan(sysinfo.t_go), o.t_act = o.T + 1000; else, o.t_act = sysinfo.t_go; end
        res.o = o;
    end
end
E = cg_auto_eval(mk, o, t, X, Y, psi, vx, info);
ic = find(res.commit > 0.5, 1);
E.commit_t = NaN;  if ~isempty(ic), E.commit_t = t(ic); end
E.areq_max = max([0; res.areq(t >= o.t_act)]);
res.metrics = E;
if ~o.quiet
    fprintf('\n  obstacle demand           : worst required deceleration %.1f m/s^2, commanded up to %.1f m/s^2\n', E.areq_max, E.decel_max);
    fprintf('  decision                  : %s\n', ternary(isnan(E.commit_t), 'stay in lane (no room to the right, or the right side was occupied)', sprintf('moved right at t = %.1f s', E.commit_t)));
    fprintf('  stopped                   : %s\n', ternary(isnan(E.tstop), sprintf('NO (still %.1f m/s at the end)', E.v_end), sprintf('%.1f s after the take-over, %.1f m travelled', E.tstop, E.stopdist)));
    if ~isempty(sysinfo) && o.sys ~= 0, printTimeline(sysinfo, o, E); end
    if ~isempty(E.lane), fprintf('  final position            : %s (%.1f m from the original lane centre; road position %.1f m -> %.1f m)\n', E.lane, E.lat_end - E.lat_start, E.lat_start, E.lat_end); end
    if E.pre_takeover
        fprintf('  NOTE                      : the ego touched another actor BEFORE the take-over (scene problem, not counted)\n');
    end
    if E.collision
        fprintf('  RESULT                    : COLLISION with %s (%.1f m ahead, %.1f m left of the ego) at t = %.1f s, impact %.1f m/s (%d object(s) hit)\n', E.hit_role, E.hit_rel(1), E.hit_rel(2), E.first_t, E.impact, E.n_collisions);
    else
        fprintf('  RESULT                    : no collision (closest approach %.1f m centre to centre, %.2f m between the car bodies%s)  [sim took %.0f s]\n', E.min_dist, E.min_gap, ...
            ternary(isfinite(E.min_dist_ped), sprintf(', pedestrian %.1f m centre / %.2f m body', E.min_dist_ped, E.min_gap_ped), ''), tsim);
    end
end
if o.plot, plotRun(res, o); end
end

function plotRun(res, o)
E = res.metrics;  t = res.t;  info = res.info;
f = figure('Visible', 'off', 'Position', [50 50 1300 800]);  tl = tiledlayout(f, 2, 2, 'TileSpacing', 'compact');
nexttile;  hold on;
if isfield(info, 'xd')
    nx = -sin(info.hd);  ny = cos(info.hd);
    for q = [-info.nl/2, -info.nl/2 + (1:info.nl)] * info.lw
        plot(info.xd + q * nx, info.yd + q * ny, 'Color', [0.7 0.7 0.7]);
    end
end
for q = 1:numel(E.tracks)
    c = [0.9 0.5 0];  if E.tracks(q).cls == 4, c = [0.8 0 0.8]; end
    plot(E.tracks(q).x, E.tracks(q).y, '-', 'Color', c);  plot(E.tracks(q).x(end), E.tracks(q).y(end), 's', 'Color', c, 'MarkerFaceColor', c, 'MarkerSize', 4);
end
plot(res.X, res.Y, 'b', 'LineWidth', 1.8);  plot(res.X(end), res.Y(end), 'bs', 'MarkerFaceColor', 'b');
axis equal;  grid on;  title('Bird''s eye: ego (blue), cars (orange), pedestrians (magenta)');  xlabel x;  ylabel y;
xlim([min(res.X) - 60, max(res.X) + 120]);
nexttile;  plot(t, res.vx, 'b', t, res.vref, 'r--');  grid on;  xline(o.t_act, 'r');  legend('speed', 'reference');  title('Speed (m/s)');  xlabel t
nexttile;  plot(t, res.adem, 'k', t, res.acmd, 'r', t, -res.areq, 'c');  grid on;  xline(o.t_act, 'r');  legend('demand', 'command', '-required for worst obstacle');  title('Longitudinal (m/s^2)');  xlabel t
nexttile;  yyaxis left;  plot(t, rad2deg(res.delta), 'b');  ylabel('steering (deg)');  yyaxis right;  plot(t, res.commit, 'g', t, res.occ, 'm', 'LineWidth', 1.2);  ylim([-0.1 1.1]);
ylabel('flags');  grid on;  xline(o.t_act, 'r');  title('Steering; green = moved right, magenta = right side occupied');  xlabel t
title(tl, sprintf('%s   |   %s', info.title, ternary(E.collision, 'COLLISION', 'no collision')));
fn = fullfile('results', sprintf('auto_%s.png', o.name));
try, exportgraphics(f, fn, 'Resolution', 110);  fprintf('  figure: %s\n', fn); catch, fprintf('  (picture could not be saved)\n'); end
close(f);
end

function v = ternary(c, a, b)
if c, v = a; else, v = b; end
end

function signs = getSigns(o) %#ok<INUSD>
fn = fullfile('results', 'dsd_signs.mat');
if isfile(fn), S = load(fn);  signs = S.signs; else, signs = cg_dsd_signs(); end
end

function I = sysTimeline(SL, o)
% first time each CabinGuard event happens (columns of syslog: see cg_auto_system)
tt = SL(:,1);
f = @(c, th) firstT(tt, SL(:,c) >= th);
I = struct('t_on', o.t_on, 'ev', o.ev, 't_alert', f(2, 1), 't_hazard', f(2, 2), 't_brake', f(2, 3), 't_stop_state', f(2, 4), ...
           't_go', f(4, 0.5), 't_ecall', f(6, 0.5), 't_delivered', f(7, 0.5), 'nrej', max(SL(:,9)), 'alive_lost', max(SL(:,10)) > 0.5, ...
           'dmode', max(SL(:,11)), 'warn', max(SL(:,14)) > 0.5, 'gwp_max', max(SL(:,3)), 'state_max', max(SL(:,2)));
end

function t = firstT(tt, c)
i = find(c, 1);
if isempty(i), t = NaN; else, t = tt(i); end
end

function printTimeline(I, o, E)
ev = {'none (conscious driver)', 'syncope', 'seizure'};
fprintf('  CabinGuard chain          : driver event = %s, fault = %d, detector delay %.1f s\n', ev{I.ev + 1}, o.fault, o.det_delay);
fprintf('  timeline [s]              : onset %.1f | ALERT %s | HAZARD %s | BRAKE %s | take-over (Gateway accepted) %s\n', I.t_on, tx(I.t_alert), tx(I.t_hazard), tx(I.t_brake), tx(I.t_go));
fprintf('  e-call                    : placed %s, delivered %s | Gateway rejected %d frame(s) | host lost: %d | warn-only: %d | degraded mode max: %d\n', tx(I.t_ecall), tx(I.t_delivered), I.nrej, I.alive_lost, I.warn, I.dmode);
if ~isnan(I.t_go) && ~isnan(E.tstop) && I.ev ~= 0
    fprintf('  incapacitation -> standstill: %.1f s in total (%.1f s detection + confirmation + warning, %.1f s braking)\n', I.t_go + E.tstop - I.t_on, I.t_go - I.t_on, E.tstop);
end
if isnan(I.t_go), fprintf('  take-over                 : NEVER requested (%s)\n', ternary(I.ev == 0, 'correct for a conscious driver', 'the chain did not act!')); end
end

function s = tx(x)
if isnan(x), s = '-'; else, s = sprintf('%.1f', x); end
end
