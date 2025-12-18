motor_table = {'zpssx':('inenc2_val',-1e-4*0.9542,'/INENC2.VAL.Value'), #-9.7e-5), # Additional correction ratio here should match with changes to the CapSensorVtoUM scaling factor in Power PMAC config files to ensure scan input and readback positions match.
            'zpssy':('inenc3_val',-1.03297e-4,'/INENC3.VAL.Value'), #-1.006e-4),
            'zpssz':('inenc4_val',1e-4,'/INENC4.VAL.Value'), #1.04e-4),
            'dssx':('inenc2_val',-1e-4,'/INENC2.VAL.Value'),
            'dssy':('inenc3_val',1e-4,'/INENC3.VAL.Value'),
            'dssz':('inenc4_val',1e-4*1.047,'/INENC4.VAL.Value'), # See above comment for correction ratio.

            # ss* stages' position readout cannot be collected by PandABox encoder inputs, make the position 1 here and calculate with softwaer instead
            'ssx':('inenc2_val',1e-4,'/INENC2.VAL.Value'),
            'ssy':('inenc3_val',1e-4,'/INENC3.VAL.Value'),
            'ssz':('inenc4_val',1e-4,'/INENC4.VAL.Value'), # See above comment for correction ratio.

            # pt_tomo_ssx conversion ratio prior to Nov. 2025 was set to -1*current value because the image recorded from eiger1_mobile detector was not mirrored
            'pt_tomo_ssx':('inenc2_val',-1e-4,'/INENC2.VAL.Value'),
            'pt_tomo_ssy':('inenc4_val',-1e-4,'/INENC4.VAL.Value')

            # Stage encoder
            #'pt_tomo_ssy':('inenc4_val',6e-5)

            # Scanning MLL setup
            #'pt_tomo_ssx':('inenc1_val',-1e-4, '/INENC1.VAL.Value'),
            #'pt_tomo_ssy':('inenc2_val',-1e-4, '/INENC2.VAL.Value')
            }
