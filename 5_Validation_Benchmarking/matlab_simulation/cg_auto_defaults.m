function cg_auto_defaults(force)
% CG_AUTO_DEFAULTS  Defines the base-workspace constants (ca_*) that CabinGuardAuto needs.
%   cg_auto_defaults        : only the ones that are missing (use after "clear all" / a restart, before pressing Run in Simulink)
%   cg_auto_defaults(true)  : resets ALL of them to the design values (cg_auto_run does this before every run)
if nargin < 1, force = false; end
defs = {'ca_v0', 15; 'ca_psi0', 0; 'ca_X0', 0; 'ca_Y0', 0; 'ca_ego_id', 1; 'ca_t_act', 5; 'ca_a_comf', 3.2; 'ca_clear', 5.4; 'ca_edge', 1.8; ...
        'ca_min_shift', 2.2; 'ca_hw', 1.5; 'ca_d0', 5; 'ca_wn', 1.0; 'ca_lka_in', 1; 'ca_lka_out', 1; 'ca_a_lo', -9; 'ca_lka_beh', 0.3; 'ca_lka_lag', 0.1; ...
        'ca_jdn', 20; 'ca_jup', 5; 'ca_lw0', 3.6; 'ca_absvel', 0; 'ca_vlat', 1.8; 'ca_kfeas', 0.8; 'ca_plant', 1; 'ca_sys', 0; 'ca_go_phase', 3; 'ca_pv', [0;0;15;0;1;4;-3;0;2;0;2;0;2;2;1]; 'ca_det', [1;1;0;0;0]};
for k = 1:size(defs, 1)
    if force || ~evalin('base', sprintf('exist(''%s'',''var'')', defs{k,1})), assignin('base', defs{k,1}, defs{k,2}); end
end
end
