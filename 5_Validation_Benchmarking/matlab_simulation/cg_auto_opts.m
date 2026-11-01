function o = cg_auto_opts(o)
% CG_AUTO_OPTS  Default options of the autonomous take-over tests (CabinGuardAuto).
%   type   : 'highway' | 'rural' | 'city'   (random scene generator)       file : name of a scenario exported from the
%   ego    : ActorID of the ego car in an exported scenario ([] = the one the export returns, else actor 1)
%   seed   : scene number                                                         Driving Scenario Designer (overrides type)
%   v0     : start speed [] = from the scene       T : stop time [] = from the scene       t_act : driver becomes unresponsive [s]
%   a_comf : comfortable minimum-risk deceleration magnitude [m/s^2]
%   content: 'random' | 'empty' | 'stopped' | 'ped' | 'follower' | 'rightcar'  (fixed single-situation tests)
%   plant  : 1 = detailed longitudinal plant (Vehicle Dynamics Blockset), 0 = simple plant, [] = as built
%   sys    : 0 = take-over at the fixed time t_act (old tests) | 1 = take-over requested by the CabinGuard chain
%            (Driver incapacitated at t_on -> detector -> Host -> Gateway -> brake phase go_phase)
%   t_on, ev : incapacitation start [s] and type (1 syncope, 2 seizure, 0 none = conscious driver)
%   fault, t_fault : 0 none, 1 camera lost, 2 IMU lost, 3 seat lost, 4 host hang, 5 forged cmd, 6 replayed cmd, 7 implausible decel,
%            8 cellular down, 9 camera blinded, 10 all bearers down, 11 phase skipped
%   t_can  : conscious driver brakes at this time (false-alarm cancel);  fa = [start dur mode] false detector evidence (mode 1 camera only, 2 all)
%   det_delay : delay of the detector after the onset [s];  alert_s / brake_s : ALERT length and ALERT-to-BRAKE time [s];  go_phase : 2 HAZARD, 3 BRAKE
%   profile: '' (design values of the simulation) | 'github' = values of the Python system (alert_s 4, brake_s 10, MRM -3.2 m/s^2,
%            detector latency of the fused AI: syncope 12.0 s, seizure 12.5 s median, 100 km/h on the highway, T 45 s)
%   mode   : 'full' (brake + move right when free) | 'brake_only' (never leaves the lane; for comparison)
d = struct('type', 'highway', 'seed', 1, 'file', '', 'ego', [], 'v0', [], 'T', [], 't_act', 5, 'a_comf', 3.2, 'e1_0', 0, 'dpsi0', 0, ...
           'mode', 'full', 'content', 'random', 'accel', true, 'plot', true, 'quiet', false, 'name', 'auto', 'wn', 1.4, 'plant', [], ...
           'sys', 0, 't_on', 2, 'ev', 1, 'fault', 0, 't_fault', 2, 't_can', 0, 'det_delay', 1.0, 'fa', [0 0 0], 'go_phase', 3, ...
           'alert_s', 2, 'brake_s', 4, 'mrm_decel', -3, 'tonic_s', 2, 'host_on', 1, 'profile', '');
if nargin < 1 || isempty(o), o = struct(); end
f = fieldnames(d);
for k = 1:numel(f)
    if ~isfield(o, f{k}), o.(f{k}) = d.(f{k}); end
end
if strcmpi(o.profile, 'github')
    lat = 12.0;  if o.ev == 2, lat = 12.5; end        % measured median latency onset -> verified event (results/fusion_metrics.json)
    o.alert_s = 4;  o.brake_s = 10;  o.mrm_decel = -3.2;  o.a_comf = 3.2;
    o.det_delay = lat - 3;                              % chain adds 1 s evidence ramp + 2 s verification = 3 s
    if strcmpi(o.type, 'highway') && isempty(o.v0) && isempty(o.file), o.v0 = 100/3.6; end
    if isempty(o.T), o.T = 45; end
end
end
