function cg_final_run(level)
% CG_FINAL_RUN  Runs the scenarios chosen for the paper and collects all results in results_final/.
%   cg_final_run('fast')  : chain unit tests + 5 closed-loop cases with the GitHub (Python) timings        (about 15 min)
%   cg_final_run('all')   : fast + the 20-case design-value suite + 9 random scenes with the GitHub timings (about 2 to 3 hours)
%   Every stage is protected: if one stage fails, the error is printed and the next stage still runs.
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
if nargin < 1, level = 'fast'; end
out = fullfile(here, 'results_final');  if ~exist(out, 'dir'), mkdir(out); end
diary(fullfile(out, 'console_log.txt'));
cleanup = onCleanup(@() diary('off'));
fprintf('CabinGuard final run, level %s, %s\n', level, datestr(now));

stage('1 chain unit tests (no Simulink)', @() cg_sys_unittest, out, 'unit_tests');
stage('2 closed loop, GitHub timings (syncope, seizure, conscious, camera lost, cellular down)', @() cg_auto_suite('github'), out, 'suite_github');
if strcmp(level, 'all')
    stage('3 closed loop, design values, 20 cases', @() cg_auto_suite('full'), out, 'suite_design');
    stage('4 random scenes, GitHub timings (3 highway, 3 rural, 3 city, full manoeuvre)', ...
          @() cg_auto_batch(3, {'highway', 'rural', 'city'}, {'full'}, 1:3, struct('sys', 1, 'ev', 1, 'profile', 'github')), out, 'batch_github');
end
fprintf('\nDONE. Everything is in %s\n', out);
end

function stage(name, fcn, out, tag)
fprintf('\n=================== %s ===================\n', name);
try
    fcn();
    copy_results(out, tag);
catch e
    fprintf('STAGE FAILED: %s\n', e.message);
end
end

function copy_results(out, tag)
% every stage writes into results/ ; keep a copy per stage
here = fileparts(mfilename('fullpath'));  src = fullfile(here, 'results');
if ~exist(src, 'dir'), return, end
dst = fullfile(out, tag);  if ~exist(dst, 'dir'), mkdir(dst); end
copyfile(fullfile(src, '*'), dst);
end
