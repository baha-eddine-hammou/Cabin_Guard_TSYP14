function r = cg_dsd_diag(i, nn)
% CG_DSD_DIAG  Replays case i of cg_dsd_eval2 (normal cases 1-24, stress 25-32) and shows where and why it stops.
%   cg_dsd_diag(5)        % expert on case 5
%   cg_dsd_diag(5, true)  % network on case 5
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
if nargin < 2, nn = false; end
nIn = 24;  stress = i > nIn;
rs = RandStream('mt19937ar', 'Seed', 9000 + i);
U = @(a, b) a + (b - a) * rand(rs);
if stress, Rm = U(100, 150); v0 = U(20, 24); else, Rm = U(150, 450); v0 = U(9, 20); end
o = struct('road', 'random', 'seed', 2000 + i, 'Rmin', Rm, 'v0', v0, 't_act', U(3, 6), 'a_mrm', -U(2.2, 3.8), 'shoulder', rand(rs) > 0.4, ...
           'e1_0', U(-0.8, 0.8), 'dpsi0', deg2rad(U(-3, 3)), 'gap0', 40, 'tau', 2.5, 'plot', true, 'quiet', false, 'accel', false, 'nn', nn, 'name', sprintf('diag%d', i));
o.T = ceil(o.t_act + o.v0 / abs(o.a_mrm) + 2.5);
fprintf('Case %d: v0 %.1f m/s, Rmin %.0f m, hazard at %.1f s, a_mrm %.1f, %s, start error %.2f m / %.1f deg, driver: %s\n', i, o.v0, o.Rmin, o.t_act, o.a_mrm, ...
    ternary(o.shoulder, 'shoulder', 'in lane'), o.e1_0, rad2deg(o.dpsi0), ternary(nn, 'network', 'expert'));
r = cg_dsd_run(o);
if r.crashed
    k = max(1, numel(r.t) - 40);  tt = r.t(k:end);
    fprintf('\nLast 0.8 s before the stop (every 0.1 s):\n  t       lateral(m)  speed   steer_cmd(deg)  steer(deg)\n');
    for q = k:5:numel(r.t), fprintf('  %5.2f   %7.2f   %6.2f   %9.2f   %9.2f\n', r.t(q), r.lat(q), r.vx(q), rad2deg(r.steer_cmd(q)), rad2deg(r.delta(q))); end
end
end

function v = ternary(c, a, b)
if c, v = a; else, v = b; end
end
