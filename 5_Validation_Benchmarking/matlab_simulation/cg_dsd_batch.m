function T = cg_dsd_batch(accel)
% CG_DSD_BATCH  Closed-loop matrix: 6 roads x {stop in lane, stop on shoulder}, with a CLOSE follower (12 m behind, reacts after 2.5 s).
%   Prints one table, saves results/dsd_batch.csv. About 1 min per run (less with accel = true).
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
if nargin < 1, accel = true; end
roads = {'scurve', 1; 'random', 1; 'random', 2; 'random', 3; 'random', 4; 'random', 5};
rows = {};
for i = 1:size(roads, 1)
    for sh = [false true]
        o = struct('road', roads{i,1}, 'seed', roads{i,2}, 'shoulder', sh, 'gap0', 12, 'tau', 2.5, 'plot', false, 'quiet', true, 'accel', accel, 'T', 14);
        try
            t0 = tic;  r = cg_dsd_run(o);  q = r.metrics;
            rows(end+1, :) = {roads{i,1}, roads{i,2}, ternary(sh, 'shoulder', 'in lane'), q.max_lat_err_before, q.tstop, q.stopdist, q.lat_end, q.collision, q.impact, q.min_gap}; %#ok<AGROW>
            fprintf('%-7s seed %d %-9s  lane err %.2f m  stop %.1f s  lat %.2f m  collision %d  impact %.1f m/s  (%.0f s)\n', roads{i,1}, roads{i,2}, ternary(sh, 'shoulder', 'in lane'), ...
                q.max_lat_err_before, q.tstop, q.lat_end, q.collision, q.impact, toc(t0));
        catch e
            fprintf('%-7s seed %d %-9s  FAILED: %s\n', roads{i,1}, roads{i,2}, ternary(sh, 'shoulder', 'in lane'), strtok(e.message, newline));
            rows(end+1, :) = {roads{i,1}, roads{i,2}, ternary(sh, 'shoulder', 'in lane'), NaN, NaN, NaN, NaN, NaN, NaN, NaN}; %#ok<AGROW>
        end
    end
end
T = cell2table(rows, 'VariableNames', {'road', 'seed', 'mode', 'lane_err_m', 'stop_s', 'stop_dist_m', 'lat_end_m', 'collision', 'impact_ms', 'min_gap_m'});
writetable(T, fullfile('results', 'dsd_batch.csv'));
disp(T);
inl = strcmp(T.mode, 'in lane');  shd = strcmp(T.mode, 'shoulder');
fprintf('\nIn lane  : %d of %d runs with collision, mean impact %.1f m/s\n', nansum(T.collision(inl)), nnz(inl), mean(T.impact_ms(inl), 'omitnan'));
fprintf('Shoulder : %d of %d runs with collision, mean impact %.1f m/s\n', nansum(T.collision(shd)), nnz(shd), mean(T.impact_ms(shd), 'omitnan'));
end

function v = ternary(c, a, b)
if c, v = a; else, v = b; end
end
