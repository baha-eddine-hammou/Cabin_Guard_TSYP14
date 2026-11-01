function sc = cg_dsd_export(o, withNN)
% CG_DSD_EXPORT  Makes the Driving Scenario COMPLETE for the Driving Scenario Designer app:
%   runs the closed-loop Simulink model, then rebuilds the scenario with the ego car driving the path
%   that the Simulink controller actually produced (plus the scripted follower), and opens it in the app.
%   In the plain scenario the ego has no trajectory because it is driven from Simulink - that is why it looked incomplete.
%   Saves results/dsd_scenario_<name>.mat (variable sc).   Example:  cg_dsd_export(struct('shoulder', true))
here = fileparts(mfilename('fullpath'));  cd(here);  addpath(here);
if nargin < 1, o = struct(); end
if nargin < 2, withNN = false; end
d = struct('road', 'random', 'seed', 3, 'gap0', 12, 'tau', 2.5, 'T', 14, 'accel', true, 'plot', false, 'quiet', true, 'shoulder', true, 'name', 'export');
f0 = fieldnames(o);  for k = 1:numel(f0), d.(f0{k}) = o.(f0{k}); end
d.nn = withNN;
r = cg_dsd_run(d);
[sc, info] = cg_dsd_scenario(d);
% ego trajectory from the logged motion, one waypoint every 0.5 s while it is moving
k = 1:25:numel(r.t);
x = r.X(k);  y = r.Y(k);  v = r.vx(k);
last = find(v < 0.6, 1);  if isempty(last), last = numel(k); end
x = x(1:last);  y = y(1:last);  v = max(v(1:last), 0.6);
keep = [true; hypot(diff(x), diff(y)) > 0.05];
trajectory(sc.Actors(1), [x(keep) y(keep) zeros(nnz(keep), 1)], v(keep));
sc.StopTime = d.T;
fn = fullfile('results', sprintf('dsd_scenario_%s.mat', ternary(d.shoulder, 'shoulder', 'inlane')));
save(fn, 'sc', 'info');
fprintf('Scenario saved: %s\n', fullfile(here, fn));
assignin('base', 'cg_scn_full', sc);
opened = false;
try
    drivingScenarioDesigner(sc);  opened = true;
catch e
    fprintf('The app did not accept the scenario object (%s).\n', strtok(e.message, newline));
end
if ~opened
    % fallback: play it with the built-in chase view
    f = figure('Name', 'Driving scenario (ego on the Simulink path)');
    ax = axes(f);  chasePlot(sc.Actors(1), 'Parent', ax);
    restart(sc);
    while advance(sc)
        drawnow limitrate;  pause(0.02);
    end
end
fprintf('In the app: press Run. To add sensors (needed only to look at them): Add Camera / Add Radar, mount the camera at x=2.2 m facing forward, the radar at x=-1 m facing backward (Yaw 180).\n');
end

function v = ternary(c, a, b)
if c, v = a; else, v = b; end
end
