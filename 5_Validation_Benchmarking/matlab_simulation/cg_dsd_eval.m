function T = cg_dsd_eval
% CG_DSD_EVAL  Expert (LKA MPC + PID) against the learned network, on roads the network never saw (seeds 1001-1006).
%   Same hazard, shoulder stop, close follower (12 m, reacts after 2.5 s). The Gateway clamp and standstill logic stay around the network.
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
if ~isfile(fullfile('results', 'dsd_nn.mat')), error('Train first: cg_dsd_train'); end
rows = {};
for seed = 1001:1006
    for nn = [false true]
        o = struct('road', 'random', 'seed', seed, 'Rmin', 250, 'shoulder', true, 'gap0', 12, 'tau', 2.5, 'T', 14, 'e1_0', 0.4 * (-1)^seed, ...
                   'plot', false, 'quiet', true, 'accel', true, 'nn', nn);
        try
            r = cg_dsd_run(o);  q = r.metrics;
            rows(end+1, :) = {seed, ternary(nn, 'network', 'expert'), q.max_lat_err_before, q.tstop, q.stopdist, q.lat_end, q.max_steer_deg, q.collision, q.side_clear}; %#ok<AGROW>
            fprintf('seed %d %-8s lane err %.2f m  stop %.1f s / %.0f m  end lat %.2f m  max steer %.1f deg  collision %d  side %.2f m\n', seed, ternary(nn, 'network', 'expert'), ...
                q.max_lat_err_before, q.tstop, q.stopdist, q.lat_end, q.max_steer_deg, q.collision, q.side_clear);
        catch e
            fprintf('seed %d %-8s FAILED: %s\n', seed, ternary(nn, 'network', 'expert'), strtok(e.message, newline));
            rows(end+1, :) = {seed, ternary(nn, 'network', 'expert'), NaN, NaN, NaN, NaN, NaN, NaN, NaN}; %#ok<AGROW>
        end
    end
end
T = cell2table(rows, 'VariableNames', {'seed', 'driver', 'lane_err_m', 'stop_s', 'stop_dist_m', 'lat_end_m', 'max_steer_deg', 'collision', 'side_clear_m'});
writetable(T, fullfile('results', 'dsd_eval.csv'));  disp(T);
for d = {'expert', 'network'}
    k = strcmp(T.driver, d{1});
    fprintf('%-8s: lane error mean %.3f m, shoulder reached %d of %d, collisions %d\n', d{1}, mean(T.lane_err_m(k), 'omitnan'), nnz(T.lat_end_m(k) < -2.7), nnz(k), nansum(T.collision(k)));
end
end

function v = ternary(c, a, b)
if c, v = a; else, v = b; end
end
