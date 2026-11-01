function cg_dsd_bus
% CG_DSD_BUS  Creates the ego-pose bus object that the Scenario Reader needs on its input port.
els = {'ActorID', 1; 'Position', [1 3]; 'Velocity', [1 3]; 'Roll', 1; 'Pitch', 1; 'Yaw', 1; 'AngularVelocity', [1 3]};
be = Simulink.BusElement.empty;
for k = 1:size(els, 1)
    e = Simulink.BusElement;  e.Name = els{k, 1};  e.Dimensions = els{k, 2};  e.DataType = 'double';  be(k) = e;
end
cgEgoIn = Simulink.Bus;  cgEgoIn.Elements = be;
assignin('base', 'cgEgoIn', cgEgoIn);
end
