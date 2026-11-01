function cg_dsd_profile
% CG_DSD_PROFILE  Runs one 6 s closed-loop run under the MATLAB profiler (normal mode) and prints the 12 biggest time users.
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
cg_dsd_run(struct('T', 1, 'plot', false, 'quiet', true));          % warm-up (compile etc.), not profiled
profile off;  profile clear;  profile on;
cg_dsd_run(struct('T', 6, 'plot', false, 'quiet', true));
profile off;
p = profile('info');  ft = p.FunctionTable;
[~, i] = sort([ft.TotalTime], 'descend');
fprintf('\n%-8s %-8s %-7s %s\n', 'total_s', 'self_s', 'calls', 'function');
for k = 1:min(25, numel(i))
    f = ft(i(k));
    n = f.FunctionName;  if numel(n) > 90, n = [n(1:45) ' ... ' n(end-40:end)]; end
    fprintf('%-8.2f %-8.2f %-7d %s\n', f.TotalTime, f.TotalTime - sum([f.Children.TotalTime]), f.NumCalls, n);
end
end
