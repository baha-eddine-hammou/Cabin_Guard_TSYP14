function signs = cg_dsd_signs
% CG_DSD_SIGNS  Finds the sign convention of the Lane Keeping Assist block by closed-loop test: straight road, ego starts 0.8 m to the
%   left of the lane centre with no hazard. The combination that brings the car back to the centre is kept (results/dsd_signs.mat).
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
if ~isfolder('results'), mkdir('results'); end
combos = [1 1; -1 -1; 1 -1; -1 1];  score = inf(4, 1);
fprintf('Testing LKA sign conventions (4 short runs)...\n');
for k = 1:4
    fn = fullfile('results', 'dsd_signs.mat');  signs = combos(k, :);  save(fn, 'signs');
    try
        r = cg_dsd_run(struct('road', 'straight', 'T', 12, 't_act', 1e6, 'e1_0', 0.8, 'plot', false, 'quiet', true, 'tau', 100));
        tt = r.t;  score(k) = mean(abs(r.lat(tt > 9)));
        fprintf('  inputs %+d, output %+d : mean |lateral error| in the last 3 s = %.3f m\n', combos(k, 1), combos(k, 2), score(k));
    catch e
        fprintf('  inputs %+d, output %+d : run failed: %s\n', combos(k, 1), combos(k, 2), e.message);
        if k == 1, rethrow(e); end
    end
end
[best, i] = min(score);  signs = combos(i, :);  save(fullfile('results', 'dsd_signs.mat'), 'signs');
fprintf('Chosen: inputs %+d, output %+d (error %.3f m).\n', signs(1), signs(2), best);
if best > 0.3, fprintf('WARNING: no combination keeps the lane well (best %.2f m). Send me this output.\n', best); end
end
