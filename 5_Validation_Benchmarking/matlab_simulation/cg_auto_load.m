function [sc, info, mk] = cg_auto_load(spec, o)
% CG_AUTO_LOAD  Loads a scenario you designed in the Driving Scenario Designer.
%   In the app:  Save > Export MATLAB Function ("Export > MATLAB Function"), e.g. as  myRoad.m
%   Then:        cg_auto_run(struct('file','myRoad'))
%   The ego car of the scenario (the one you marked as ego, or actor 1) is driven by the Simulink model;
%   its own path in the app is only used for the start position and heading.
if nargin < 2, o = struct(); end
o = cg_auto_opts(o);
if ischar(spec) || isstring(spec), f = str2func(char(spec)); else, f = spec; end
mk = @() loadOne(f, o);
[sc, info] = mk();
end

function [sc, info] = loadOne(f, o)
% The function written by the app ("Export > Export MATLAB Function") returns [allData, scenario, sensors].
% It also plays the scenario once to record sensor data, so the scenario is restarted afterwards.
sc = [];  ego = [];
out = cell(1, 3);
try
    [out{1:3}] = f();
catch
    out = cell(1, 3);
    try, [out{1:2}] = f(); catch, out{1} = f(); end
end
for k = 1:numel(out)
    if isa(out{k}, 'drivingScenario'), sc = out{k}; break, end
end
if isempty(sc), error('The function %s does not return a drivingScenario object.', func2str(f)); end
for k = 1:numel(out)
    if isa(out{k}, 'driving.scenario.Vehicle') || isa(out{k}, 'driving.scenario.Actor'), ego = out{k}; end
end
try, restart(sc); catch, end
if isempty(ego)
    ego = sc.Actors(1);
    for k = 1:numel(sc.Actors)      % prefer the car the app calls the vehicle under test / ego
        nm = lower(char(string(sc.Actors(k).Name)));
        if contains(nm, 'under test') || strcmp(nm, 'ego') || contains(nm, 'ego')
            ego = sc.Actors(k); break
        end
    end
end
try, sc.SampleTime = 0.1; catch, end
if ~isempty(o.ego)
    ego = sc.Actors([sc.Actors.ActorID] == o.ego);
    if isempty(ego), error('The scenario has no actor with ID %d (it has %d actors).', o.ego, numel(sc.Actors)); end
end
info = struct('egoID', ego.ActorID, 'v0', [], 'type', 'file', 'title', 'exported scenario', 'desc', {{'exported scenario'}});
n = norm(ego.Velocity(1:2));  if n > 1, info.v0 = n; end
T = o.T;  if isempty(T), T = 20; end
info.T = T;
try, sc.StopTime = T; catch, end
end
