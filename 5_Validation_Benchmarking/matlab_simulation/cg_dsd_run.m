function res = cg_dsd_run(o)
% CG_DSD_RUN  One closed-loop run of CabinGuardDSD on a Driving Scenario road. Prints metrics, draws results/dsd_<name>.png.
%   o fields (all optional, see cg_dsd_opts): road ('straight'|'scurve'|'random'), seed, v0, T, t_act, a_mrm, shoulder, tau, gap0, e1_0 ...
%   Examples:  cg_dsd_run                                    % S-curve, shoulder stop, follower reacts after 1.5 s
%              cg_dsd_run(struct('road','random','seed',3))
%              cg_dsd_run(struct('shoulder',false))          % stop in lane
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
if ~isfolder('results'), mkdir('results'); end
if nargin < 1, o = struct(); end
o = cg_dsd_opts(o);
m = 'CabinGuardDSD';
if ~isfile(fullfile(here, [m '.slx'])), cg_dsd_build(m); end
if ~bdIsLoaded(m), load_system(fullfile(here, m)); end
if ~o.fast, try, set_param(m, 'FastRestart', 'off'); catch, end, end      % a failed earlier run can leave Fast Restart on
signs = getSigns(o);
[sc, info] = cg_dsd_scenario(o);
cg_dsd_bus();
lw = info.lw;
x0 = info.x0 - sin(info.psi0) * o.e1_0;  y0 = info.y0 + cos(info.psi0) * o.e1_0;
vars = {'cg_scn', sc; 'cg_v0', o.v0; 'cg_psi0', info.psi0 + o.dpsi0; 'cg_X0', x0; 'cg_Y0', y0; 'cg_t_act', o.t_act; 'cg_a_mrm', o.a_mrm; ...
        'cg_ysh', lw * double(o.shoulder); 'cg_lw', lw; 'cg_jump_thr', 0.75 * lw; 'cg_wn', o.wn; 'cg_lka_in', signs(1); 'cg_lka_out', signs(2); 'cg_ctl_mode', double(o.nn)};
for k = 1:size(vars, 1), assignin('base', vars{k,1}, vars{k,2}); end
if o.nn
    S = load(fullfile('results', 'dsd_nn.mat'));  assignin('base', 'cg_nn', S.cg_nn);
else
    assignin('base', 'cg_nn', cg_dsd_nn_default());
end
set_param(m, 'StopTime', num2str(o.T));
if o.accel, try, set_param(m, 'SimulationMode', 'accelerator'); catch ae, fprintf('accelerator mode not possible: %s\n', strtok(ae.message, newline)); end
else, set_param(m, 'SimulationMode', 'normal'); end
if o.fast, set_param(m, 'FastRestart', 'on'); else, set_param(m, 'FastRestart', 'off'); end
tic;  out = sim(m);  tsim = toc;
A = out.cglog;
t = (0:size(A, 1) - 1)' * 0.02;
crashed = t(end) < o.T - 0.1;                        % the guard in the model stops the run when a command is not a number
FEAT = [];  TGT = [];
try, FEAT = out.cgfeat; catch, end
try, TGT = out.cgtgt; catch, end
crashInfo = '';
if crashed
    cn = {'X','Y','psi','vx','vy','r','delta','lane offset (Vision)','tracked offset','y_ref','v_ref','a_ref','active','radar gap','radar closing speed','measured speed','accel cmd','steer cmd','follower x','follower y','follower z'};
    crashInfo = sprintf('guard stopped the run at t = %.2f s: a controller command became NaN', t(end));
    bad = find(any(~isfinite(A), 2), 1);
    if ~isempty(bad), crashInfo = sprintf('%s | first non-finite logged signal: %s at t = %.2f s', crashInfo, cn{find(~isfinite(A(bad, :)), 1)}, t(bad)); end
    fb = find(any(~isfinite(FEAT), 2), 1);  tb = find(any(~isfinite(TGT), 2), 1);
    if ~isempty(fb), crashInfo = sprintf('%s | network inputs non-finite at t = %.1f s (input %d)', crashInfo, (fb - 1) * 0.1, find(~isfinite(FEAT(fb, :)), 1)); end
    if ~isempty(tb), crashInfo = sprintf('%s | driver output non-finite at t = %.1f s (output %d)', crashInfo, (tb - 1) * 0.1, find(~isfinite(TGT(tb, :)), 1)); end
end
X = A(:,1); Y = A(:,2); vx = A(:,4); delta = A(:,7);
e1m = A(:,8); dd = A(:,9); yref = A(:,10); vref = A(:,11); aref = A(:,12); gap_r = A(:,14); acmd = A(:,17); dcmd = A(:,18);
fx = A(:,19); fy = A(:,20);
[s_e, lat] = project(info, X, Y);
res = struct('feat', FEAT, 'tgt', TGT, 'crashed', crashed, 'crash_msg', crashInfo, 't', t, 'X', X, 'Y', Y, 'vx', vx, 'lat', lat, 's', s_e, 'delta', delta, 'acmd', acmd, 'steer_cmd', dcmd, 'gap_true', -fx, 'gap_radar', gap_r, 'psi', A(:,3), 'fx', fx, 'fy', fy, 'vref', vref, 'info', info);
% metrics
ia = find(t >= o.t_act, 1);
istop = find(vx < 0.1 & t > o.t_act, 1);
if isempty(istop) || isempty(ia), tstop = NaN; sdist = NaN; else, tstop = t(istop) - o.t_act; sdist = s_e(istop) - s_e(ia); end
latEnd = lat(end);
inShoulder = latEnd < -(lw/2 + 0.9);
inLane2 = abs(latEnd) < lw/2 - 0.5;
col = find(-fx < 4.7 & abs(fy) < 1.9 & t > o.t_act, 1);
if isempty(col), impact = 0; tcol = NaN; else, impact = max(0, info.vf(t(col)) - vx(col)); tcol = t(col) - o.t_act; end
res.metrics = struct('tstop', tstop, 'stopdist', sdist, 'lat_end', latEnd, 'in_shoulder', inShoulder, 'in_lane', inLane2, 'collision', ~isempty(col), 'impact', impact, ...
    'max_lat_err_before', mxe(abs(lat(t < o.t_act))), 'lat_err_pre', mxe(abs(lat(t >= o.t_act - 1.5 & t < o.t_act))), 'min_gap', -mxe(fx(t > o.t_act)), 'v_end', vx(end), 'max_steer_deg', max(abs(rad2deg(delta))), ...
    'side_clear', sideClear(fx, fy, t, o.t_act));
if crashed && ~o.quiet, fprintf('\n*** %s\n', crashInfo); end
if ~o.quiet
    fprintf('\n=== DSD closed loop: road %s, hazard action at t=%.1f s, a_mrm %.1f, %s, follower tau %.1f s  (sim took %.1f s)\n', o.road, o.t_act, o.a_mrm, ...
        ternary(o.shoulder, 'shoulder stop', 'stop in lane'), o.tau, tsim);
    fprintf('  lane keeping before hazard : max |lateral error| = %.2f m\n', res.metrics.max_lat_err_before);
    fprintf('  stopped                    : %s\n', ternary(isnan(tstop), 'NO (still moving)', sprintf('%.1f s after hazard, %.1f m travelled', tstop, sdist)));
    fprintf('  final lateral position     : %.2f m from lane-2 centre  -> %s\n', latEnd, ternary(inShoulder, 'in the SHOULDER', ternary(inLane2, 'in the driving lane', 'between lanes')));
    if ~isnan(res.metrics.side_clear), fprintf('  follower passes alongside  : side clearance %.2f m\n', res.metrics.side_clear); end
    fprintf('  follower                   : %s\n', ternary(isempty(col), sprintf('no collision (min gap %.1f m centre to centre)', res.metrics.min_gap), sprintf('COLLISION %.1f s after hazard, impact %.1f m/s', tcol, impact)));
    fprintf('  radar gap vs truth (before braking): mean error %.2f m\n', mean(gap_r(t > 1 & t < o.t_act) - (-fx(t > 1 & t < o.t_act))));
end
if o.plot
    f = figure('Visible', 'off', 'Position', [50 50 1250 800]);  tl = tiledlayout(f, 3, 2, 'TileSpacing', 'compact');
    nexttile; hold on; plot(info.xd, info.yd, 'k:'); plot(X, Y, 'b', 'LineWidth', 1.6); axis equal; grid on; title('Path (dotted = road centre)'); xlabel x; ylabel y;
    nexttile; plot(t, lat, 'b', t, -info.lw/2*ones(size(t)), 'k:', t, info.lw/2*ones(size(t)), 'k:', t, -1.5*info.lw*ones(size(t)), 'k--'); grid on; xline(o.t_act, 'r');
    title('Lateral position (m, left +), lane edges at +-1.8, shoulder centre at -3.6'); xlabel t
    nexttile; plot(t, vx, 'b', t, vref, 'r--', t, info.vf(t), 'm'); grid on; xline(o.t_act, 'r'); legend('ego speed', 'speed reference', 'follower'); title('Speed (m/s)'); xlabel t
    nexttile; yyaxis left; plot(t, rad2deg(delta), 'b', t, rad2deg(dcmd), 'c:'); ylabel('steering (deg)'); yyaxis right; plot(t, acmd, 'r'); ylabel('accel cmd (m/s^2)'); grid on; xline(o.t_act, 'r'); title('Steering and acceleration'); xlabel t
    nexttile; plot(t, -fx, 'm', t, gap_r, 'g.', 'MarkerSize', 4); ylim([0 80]); grid on; xline(o.t_act, 'r'); legend('true distance', 'rear radar'); title('Follower: distance behind (m)'); xlabel t
    nexttile; plot(t, e1m, 'b', t, dd, 'r', t, yref, 'k--'); grid on; xline(o.t_act, 'r'); legend('Vision lane offset', 'tracked offset (continuous)', 'reference'); title('Lane offset seen by Vision (m)'); xlabel t
    title(tl, sprintf('CabinGuardDSD: %s road, %s', o.road, ternary(o.shoulder, 'shoulder MRM', 'in-lane MRM')));
    fn = fullfile('results', sprintf('dsd_%s.png', o.name));
    try
        exportgraphics(f, fn, 'Resolution', 110);
    catch
        fn = fullfile('results', sprintf('dsd_%s_%s.png', o.name, datestr(now, 'HHMMSS')));      % the old file is probably open in a viewer
        try, exportgraphics(f, fn, 'Resolution', 110); catch, fn = '(picture could not be saved)'; end
    end
    close(f);
    if ~o.quiet, fprintf('  figure: %s\n', fn); end
end
end

function [s_e, lat] = project(info, X, Y)
xd = info.xd(:)';  yd = info.yd(:)';  hd = info.hd(:)';
s_e = zeros(size(X));  lat = zeros(size(X));
for k0 = 1:2000:numel(X)
    kk = k0:min(numel(X), k0 + 1999);
    D = (X(kk) - xd).^2 + (Y(kk) - yd).^2;
    [~, j] = min(D, [], 2);
    tx = cos(hd(j))';  ty = sin(hd(j))';
    lat(kk) = tx .* (Y(kk) - yd(j)') - ty .* (X(kk) - xd(j)');
    s_e(kk) = info.sd(j);
end
end

function m = mxe(v)
if isempty(v), m = NaN; else, m = max(v); end
end

function c = sideClear(fx, fy, t, ta)
% smallest sideways gap (m, body edge to body edge) while the follower is alongside / overlapping the ego longitudinally
k = (abs(fx) < 4.7) & (t > ta);
if any(k), c = min(abs(fy(k))) - 1.8; else, c = NaN; end
end

function v = ternary(c, a, b)
if c, v = a; else, v = b; end
end

function signs = getSigns(o)
% the sign convention of the LKA block is found once by a short test and cached
fn = fullfile('results', 'dsd_signs.mat');
if isfile(fn)
    S = load(fn);  signs = S.signs;
else
    signs = cg_dsd_signs();
end
if ~o.quiet, fprintf('LKA sign convention (inputs, output): [%d %d]\n', signs(1), signs(2)); end
end
