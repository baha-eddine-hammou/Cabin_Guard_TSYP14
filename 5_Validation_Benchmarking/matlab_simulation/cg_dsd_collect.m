function cg_dsd_collect(N, first)
% CG_DSD_COLLECT  Records training data from the expert (LKA + PID) driving many random roads.
%   Each run draws a random road (radius 150-450 m), speed 9-20 m/s, hazard time, braking level, shoulder or in-lane stop,
%   and a random start error (lane offset +-0.8 m, heading +-3 deg) so that recovery situations are in the data.
%   Saves results/dsd_data/run_XXXX.mat (features 11 x samples at 10 Hz, expert outputs 2). Safe to stop and restart: finished runs are skipped.
%   cg_dsd_collect(120)       % about 1 hour
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
if nargin < 1, N = 120; end
if nargin < 2, first = 1; end
d = fullfile('results', 'dsd_data');  if ~isfolder(d), mkdir(d); end
for i = first:first + N - 1
    fn = fullfile(d, sprintf('run_%04d.mat', i));
    if isfile(fn), continue, end
    rs = RandStream('mt19937ar', 'Seed', 5000 + i);
    U = @(a, b) a + (b - a) * rand(rs);
    o = struct('road', 'random', 'seed', i, 'Rmin', U(150, 450), 'v0', U(9, 20), 't_act', U(3, 6), 'a_mrm', -U(2.2, 3.8), 'shoulder', rand(rs) > 0.4, ...
               'e1_0', U(-0.8, 0.8), 'dpsi0', deg2rad(U(-3, 3)), 'gap0', 40, 'tau', 2.5, 'plot', false, 'quiet', true, 'accel', true);
    o.T = ceil(o.t_act + o.v0 / abs(o.a_mrm) + 2.5);
    t0 = tic;
    try
        r = cg_dsd_run(o);
        if r.crashed, fprintf('run %4d FAILED (v0 %.1f, Rmin %.0f, e1_0 %.2f, dpsi %.1f deg): %s\n', i, o.v0, o.Rmin, o.e1_0, rad2deg(o.dpsi0), r.crash_msg); continue, end
        F = r.feat;  Tg = r.tgt;  metrics = r.metrics;  %#ok<NASGU>
        save(fn, 'o', 'F', 'Tg', 'metrics');
        fprintf('run %4d  v0 %4.1f  Rmin %3.0f  a %.1f  %-8s  lane err %.2f  end lat %5.2f  (%d samples, %.0f s)\n', i, o.v0, o.Rmin, o.a_mrm, ...
            tern(o.shoulder, 'shoulder', 'in lane'), metrics.max_lat_err_before, metrics.lat_end, size(F, 1), toc(t0));
    catch e
        fprintf('run %4d FAILED: %s\n', i, strtok(e.message, newline));
    end
end
fprintf('Done. %d run files in %s\n', numel(dir(fullfile(d, 'run_*.mat'))), d);
end

function v = tern(c, a, b)
if c, v = a; else, v = b; end
end
