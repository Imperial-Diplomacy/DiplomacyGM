BEGIN TRANSACTION;
UPDATE boards
SET data_file = 'impdip.1.2.chaos'
WHERE data_file = 'impdip.1.4.chaos';
COMMIT;
