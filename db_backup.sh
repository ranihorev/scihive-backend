set -e

# DB host (secondary preferred as to avoid impacting primary performance)
HOST=localhost:27017

# DB name
DBNAME=arxiv

# S3 bucket name
BUCKET=scihive-backup

# Linux user account
USER=ubuntu

# Current time
TIME=`/bin/date +%d-%m-%Y-%T`

# Backup directory
DEST=~/tmp

# Tar file of backup directory
TAR=$DEST/../$TIME.tar

# Create backup dir (-p to avoid warning if already exists)
/bin/mkdir -p $DEST

# Log
echo "Backing up $HOST/$DBNAME to s3://$BUCKET/ on $TIME";

# Dump from mongodb host into backup directory
mongodump -h $HOST -d $DBNAME -o $DEST

# Create tar of backup directory
tar cvf $TAR -C $DEST .

# Upload tar to s3
aws s3 cp $TAR s3://$BUCKET/

# Remove tar file locally
rm -f $TAR

# Remove backup directory
rm -rf $DEST

# All done
echo "Backup available at https://s3.amazonaws.com/$BUCKET/$TIME.tar"
