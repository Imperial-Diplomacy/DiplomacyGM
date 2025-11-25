BEGIN TRANSACTION;
UPDATE boards
SET data_file = 'helladip.0.2'
WHERE data_file = 'helladip.json';

UPDATE boards
SET data_file = 'impdip.1.0'
WHERE data_file = 'impdip.json';

UPDATE boards
SET data_file = 'impdip.1.1'
WHERE data_file = 'impdip1.1.json';

UPDATE boards
SET data_file = 'impdip.0.1'
WHERE data_file = 'impdip_a1.json';

UPDATE boards
SET data_file = 'impdip.1.4.chaos'
WHERE data_file = 'impdipchaos.json';

UPDATE boards
SET data_file = 'impdip.1.2.chaos.sa'
WHERE data_file = 'impdipchaos_sa.json';

UPDATE boards
SET data_file = 'impdip.1.2.fow'
WHERE data_file = 'impdipfow.json';

UPDATE boards
SET data_file = 'maddip.0.2'
WHERE data_file = 'maddip.json';

UPDATE boards
SET data_file = 'pelopondip.2.2'
WHERE data_file = 'peloponnesian_war.json';

UPDATE boards
SET data_file = 'impdip.1.2'
WHERE data_file = 'impdip.1.2.json';

UPDATE boards
SET data_file = 'impdip.1.4'
WHERE data_file = 'impdip.1.4.json';

UPDATE boards
SET data_file = 'impdip.1.5'
WHERE data_file = 'impdip.1.5.json';

UPDATE boards
SET data_file = 'impdip.2.0'
WHERE data_file = 'impdip.2.0.json';

UPDATE boards
SET data_file = 'impdip.1.6'
WHERE data_file = 'impdip.1.6.json';

UPDATE boards
SET data_file = 'helladip.0.3'
WHERE data_file = 'helladip.0.3.json';

COMMIT;
