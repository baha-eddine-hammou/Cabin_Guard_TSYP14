function T = cg_dsd_eval2(nIn, nStress)
% CG_DSD_EVAL2  Wider test of expert (LKA MPC + PID) against the learned network on conditions never used in training.
%   Group 'normal' : same ranges as the training data (radius 150-450 m, speed 9-20 m/s, random hazard time, braking, shoulder/in-lane, start error).
%   Group 'stress' : OUTSIDE the training range (radius 100-150 m, speed 20-24 m/s) - shows where each driver stops working.
%   Lane error = largest lateral error in the last 1.5 s before the hazard (after the start error has been corrected).
%   cg_dsd_eval2(24, 8)  takes about 40 minutes.
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
if nargin < 1, nIn = 24; end
if nargin < 2, nStress = 8; end
if ~isfile(fullfile('results', 'dsd_nn.mat')), error('Train first: cg_dsd_train'); end
rows = {};  n = nIn + nStress;
for i = 1:n
    stress = i > nIn;
    rs = RandStream('mt19937ar', 'Seed', 9000 + i);
    U = @(a, b) a + (b - a) * rand(rs);
    if stress, Rm = U(100, 150); v0 = U(20, 24); else, Rm = U(150, 450); v0 = U(9, 20); end
    base = struct('road', 'random', 'seed', 2000 + i, 'Rmin', Rm, 'v0', v0, 't_act', U(3, 6), 'a_mrm', -U(2.2, 3.8), 'shoulder', rand(rs) > 0.4, ...
                  'e1_0', U(-0.8, 0.8), 'dpsi0', deg2rad(U(-3, 3)), 'gap0', 40, 'tau', 2.5, 'plot', false, 'quiet', true, 'accel', true);
    base.T = ceil(base.t_act + base.v0 / abs(base.a_mrm) + 2.5);
    for nn = [false true]
        o = base;  o.nn = nn;
        who = ternary(nn, 'network', 'expert');  grp = ternary(stress, 'stress', 'normal');
        try
            r = cg_dsd_run(o);  q = r.metrics;
            if r.crashed, error('%s', r.crash_msg); end
            ok = q.lat_err_pre < 0.3 && (~o.shoulder || q.in_shoulder) && ~isnan(q.tstop);
            rows(end+1, :) = {i, grp, who, o.v0, o.Rmin, o.a_mrm, o.shoulder, q.lat_err_pre, q.tstop, q.stopdist, q.lat_end, q.max_steer_deg, ok}; %#ok<AGROW>
            fprintf('%2d %-6s %-8s v0 %4.1f Rmin %3.0f %-8s lane err %.2f  stop %.1f s  end lat %5.2f  ok %d\n', i, grp, who, o.v0, o.Rmin, ...
                ternary(o.shoulder, 'shoulder', 'in lane'), q.lat_err_pre, q.tstop, q.lat_end, ok);
        catch e
            fprintf('%2d %-6s %-8s FAILED: %s\n', i, grp, who, strtok(e.message, newline));
            rows(end+1, :) = {i, grp, who, o.v0, o.Rmin, o.a_mrm, o.shoulder, NaN, NaN, NaN, NaN, NaN, false}; %#ok<AGROW>
        end
    end
end
T = cell2table(rows, 'VariableNames', {'case', 'group', 'driver', 'v0', 'Rmin', 'a_mrm', 'shoulder', 'lane_err_m', 'stop_s', 'stop_dist_m', 'lat_end_m', 'max_steer_deg', 'ok'});
writetable(T, fullfile('results', 'dsd_eval2.csv'));
fprintf('\n%-7s %-8s %5s %8s %10s %12s %14s\n', 'group', 'driver', 'runs', 'ok', 'lane err', 'stop dist', 'end lat');
for g = {'normal', 'stress'}
    for d = {'expert', 'network'}
        k = strcmp(T.group, g{1}) & strcmp(T.driver, d{1});
        if ~any(k), continue, end
        fprintf('%-7s %-8s %5d %5d/%-2d %8.3f m %9.1f m %11.2f m\n', g{1}, d{1}, nnz(k), nnz(T.ok(k)), nnz(k), mean(T.lane_err_m(k), 'omitnan'), ...
            mean(T.stop_dist_m(k), 'omitnan'), mean(T.lat_end_m(k), 'omitnan'));
    end
end
% how close is the network to the expert, case by case
E = T(strcmp(T.driver, 'expert'), :);  N = T(strcmp(T.driver, 'network'), :);
dl = N.lat_end_m - E.lat_end_m;  ds = N.stop_dist_m - E.stop_dist_m;
fprintf('\nNetwork minus expert, same case: end position mean %.3f m (worst %.2f m), stop distance mean %.2f m (worst %.2f m)\n', ...
    mean(abs(dl), 'omitnan'), max(abs(dl)), mean(abs(ds), 'omitnan'), max(abs(ds)));
end

function v = ternary(c, a, b)
if c, v = a; else, v = b; end
end
