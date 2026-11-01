function o = cg_dsd_opts(o)
% CG_DSD_OPTS  Fills in default options for the DSD closed-loop study.
if nargin < 1 || isempty(o), o = struct(); end
d = struct('road', 'scurve', 'seed', 1, 'Rmin', 250, 'v0', 15.3, 'T', 20, 't_act', 5, 'a_mrm', -3.2, 'shoulder', true, ...
           'tau', 1.5, 'gap0', 30, 'vf0', [], 'af', 5, 'e1_0', 0, 'dpsi0', 0, 's_ego', 100, 'plot', true, 'quiet', false, 'name', 'run', 'wn', 1.0, 'accel', false, 'fast', false, 'nn', false);
f = fieldnames(d);
for k = 1:numel(f), if ~isfield(o, f{k}), o.(f{k}) = d.(f{k}); end, end
if isempty(o.vf0), o.vf0 = o.v0; end
end
