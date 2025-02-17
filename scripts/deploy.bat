@echo on
set ARCHIVE_PATH=project.tar.gz
set ENV_PATH=.env.development

echo Deploying using %ENV_PATH% to debian based machine.

echo Loading %ENV_PATH% file...
setlocal
FOR /F "tokens=*" %%i in (%ENV_PATH%) do SET %%i

echo Packing...
git archive --format=tar.gz -o %ARCHIVE_PATH% HEAD

echo Sending package...
scp -r %ARCHIVE_PATH% %SSH_USER%@%SSH_HOST%:%SSH_DIR%/%ARCHIVE_PATH%
del %ARCHIVE_PATH%

echo Stopping service...
ssh %SSH_USER%@%SSH_HOST% "systemctl stop ServerChess.service || echo 'Stopping service failed...'"

echo Unpacking...
ssh %SSH_USER%@%SSH_HOST% "cd %SSH_DIR%; tar -xzf %ARCHIVE_PATH% -C .; rm %ARCHIVE_PATH%"

echo Updating and starting service...
ssh %SSH_USER%@%SSH_HOST% "cp %SSH_DIR%/scripts/ServerChess.service /etc/systemd/system/ServerChess.service; sed -i 's/\$PROJECT_DIR/%SSH_DIR%/g' /etc/systemd/system/ServerChess.service; "
ssh %SSH_USER%@%SSH_HOST% "systemctl enable ServerChess.service || echo 'Enabling service failed...'"
ssh %SSH_USER%@%SSH_HOST% "systemctl start ServerChess.service || echo 'Starting service failed...'"

echo Finished.
