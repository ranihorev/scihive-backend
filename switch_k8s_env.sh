#!/bin/bash

if [ "$1" = "local" ]; then
    kubectl config use-context minikube
elif [ "$1" = "cloud" ]; then
    cd terraform && gcloud container clusters get-credentials $(terraform output kubernetes_cluster_name) --region $(terraform output cluster_location) && cd ..
else
    echo ERROR: Please provide a valid option - local/cloud
    exit 1
fi

kubectl config set-context --current --namespace=scihive-backend