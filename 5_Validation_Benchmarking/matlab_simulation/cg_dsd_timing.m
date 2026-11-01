function cg_dsd_timing
% CG_DSD_TIMING  Where does the run time go?  2 s runs, 20 s run, with and without Fast Restart (all in Accelerator mode).
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
base = struct('plot', false, 'quiet', true, 'accel', true);
fprintf('2 s run, normal      : '); tic; cg_dsd_run(setf(base, 'T', 2, 'fast', false)); fprintf('%.1f s\n', toc);
fprintf('20 s run, normal     : '); tic; cg_dsd_run(setf(base, 'T', 20, 'fast', false)); fprintf('%.1f s\n', toc);
set_param('CabinGuardDSD', 'FastRestart', 'off');
end
function o = setf(o, varargin)
for k = 1:2:numel(varargin), o.(varargin{k}) = varargin{k+1}; end
end
