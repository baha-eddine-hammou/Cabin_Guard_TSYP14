function T = cg_auto_batch(N, types, modes, seeds, extra)
% CG_AUTO_BATCH  Many random scenes (highway / rural / city) - each run with the full autonomous car and with "brake only".
%   cg_auto_batch(6)  : 6 scenes per type x 3 types x 2 modes = 36 runs, about 1.5 min each  (about 1 hour)
%   cg_auto_batch(6, {}, {}, 1:6, struct('sys',1,'ev',1)) : same, but the take-over is requested by the CabinGuard chain (syncope at 2 s)
%   Prints a table, saves results/auto_batch.csv and a summary. Failures are reported, not hidden.
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
if nargin < 1, N = 6; end
if nargin < 2 || isempty(types), types = {'highway', 'rural', 'city'}; end
if nargin < 3 || isempty(modes), modes = {'full', 'brake_only'}; end
if nargin < 4, seeds = 1:N; end
rows = {};
for ty = 1:numel(types)
    for sd = seeds
        for mo = 1:numel(modes)
            o = struct('type', types{ty}, 'seed', sd, 'mode', modes{mo}, 'plot', false, 'quiet', true, 'accel', true);
            if exist('extra', 'var') && isstruct(extra), fx = fieldnames(extra); for q = 1:numel(fx), o.(fx{q}) = extra.(fx{q}); end, end
            try
                t0 = tic;  r = cg_auto_run(o);  E = r.metrics;  i = r.info;
                what = sprintf('lead%d fol%d adj%d ped%d park%d dis%d', i.lead, i.follower, i.nadj, i.nped, i.nparked, i.disabled);
                rows(end+1, :) = {types{ty}, sd, modes{mo}, r.p.v0, what, E.collision, E.hit_class == 4, E.impact, E.tstop, E.stopdist, E.lane, ~isnan(E.commit_t), r.crashed}; %#ok<AGROW>
                fprintf('%-8s %2d %-10s v0 %4.1f  %-32s  %s  %s\n', types{ty}, sd, modes{mo}, r.p.v0, what, ...
                    ternary(E.collision, sprintf('COLLISION %.1f m/s with %s', E.impact, E.hit_role), ternary(E.pre_takeover, 'INVALID SCENE (contact before take-over)', 'ok')), E.lane);
            catch e
                fprintf('%-8s %2d %-10s FAILED: %s\n', types{ty}, sd, modes{mo}, strtok(e.message, newline));
                rows(end+1, :) = {types{ty}, sd, modes{mo}, NaN, 'failed', true, false, NaN, NaN, NaN, 'failed', false, true}; %#ok<AGROW>
            end
        end
    end
end
T = cell2table(rows, 'VariableNames', {'type', 'seed', 'mode', 'v0', 'scene', 'collision', 'pedestrian_hit', 'impact_ms', 'tstop_s', 'stopdist_m', 'final', 'moved_right', 'crashed'});
writetable(T, fullfile('results', 'auto_batch.csv'));
fprintf('\n%-8s %-11s %5s %10s %12s %12s\n', 'type', 'mode', 'runs', 'collisions', 'ped. hits', 'mean impact');
for ty = 1:numel(types)
    for mo = 1:numel(modes)
        q = strcmp(T.type, types{ty}) & strcmp(T.mode, modes{mo});
        fprintf('%-8s %-11s %5d %10d %12d %9.1f m/s\n', types{ty}, modes{mo}, nnz(q), nnz(T.collision(q)), nnz(T.pedestrian_hit(q)), mean(T.impact_ms(q & T.collision), 'omitnan'));
    end
end
disp(T);
end

function v = ternary(c, a, b)
if c, v = a; else, v = b; end
end
