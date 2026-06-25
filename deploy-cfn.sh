#!/usr/bin/env bash
# deploy_cfn.sh — Idempotent CloudFormation deploy with rollback handling
# Usage:
#   bash deploy_cfn.sh <STACK_NAME> <TEMPLATE_PATH> [extra aws deploy args...]

set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <STACK_NAME> <TEMPLATE_PATH> [extra aws deploy args...]" >&2
  exit 2
fi

STACK="$1"; TEMPLATE="$2"; shift 2
EXTRA_ARGS=("$@")

# Ensure region is set (repo var should provide this; default as safeguard)
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-ap-south-1}"

# Sanity: ensure access keys are present (Bitbucket repo vars)
: "${AWS_ACCESS_KEY_ID:?AWS_ACCESS_KEY_ID not set}"
: "${AWS_SECRET_ACCESS_KEY:?AWS_SECRET_ACCESS_KEY not set}"

# Optional: assume an admin role if AWS_ASSUME_ROLE_ARN is provided
if [ -n "${AWS_ASSUME_ROLE_ARN:-}" ]; then
  echo "Assuming role: $AWS_ASSUME_ROLE_ARN"
  CREDS_JSON="$(aws sts assume-role --role-arn "$AWS_ASSUME_ROLE_ARN" --role-session-name "bb-deploy-$(date +%s)")"
  export AWS_ACCESS_KEY_ID="$(echo "$CREDS_JSON" | jq -r .Credentials.AccessKeyId)"
  export AWS_SECRET_ACCESS_KEY="$(echo "$CREDS_JSON" | jq -r .Credentials.SecretAccessKey)"
  export AWS_SESSION_TOKEN="$(echo "$CREDS_JSON" | jq -r .Credentials.SessionToken)"
fi

echo "Caller identity:"
aws sts get-caller-identity

get_status () {
  aws cloudformation describe-stacks --stack-name "$STACK" \
    --query "Stacks[0].StackStatus" --output text 2>/dev/null || echo "NO_STACK"
}

in_progress () {
  case "$1" in *_IN_PROGRESS) return 0 ;; *) return 1 ;; esac
}

wait_until_stable () {
  while true; do
    s="$(get_status)"
    if in_progress "$s"; then
      echo "Waiting for stack '$STACK' to stabilize (status=$s) ..."
      sleep 10
    else
      echo "Stack '$STACK' stabilized with status: $s"
      break
    fi
  done
}

delete_if_unrecoverable () {
  s="$(get_status)"
  case "$s" in
    ROLLBACK_COMPLETE|UPDATE_ROLLBACK_COMPLETE)
      echo "Stack '$STACK' is in $s. Deleting before redeploy..."
      aws cloudformation delete-stack --stack-name "$STACK"
      aws cloudformation wait stack-delete-complete --stack-name "$STACK"
      ;;
    ROLLBACK_IN_PROGRESS|UPDATE_ROLLBACK_IN_PROGRESS)
      echo "Rollback in progress for '$STACK' ($s). Waiting..."
      wait_until_stable
      delete_if_unrecoverable
      ;;
    *)
      echo "Preflight OK for '$STACK' (status=$s)."
      ;;
  esac
}

safe_deploy () {
  set +e
  aws cloudformation deploy \
    --region "$AWS_DEFAULT_REGION" \
    --stack-name "$STACK" \
    --template-file "$TEMPLATE" \
    "${EXTRA_ARGS[@]}"
  rc=$?
  set -e
  s="$(get_status)"
  echo "Deploy exit rc=$rc; final status=$s"
  if [ $rc -ne 0 ]; then
    case "$s" in
      ROLLBACK_COMPLETE|UPDATE_ROLLBACK_COMPLETE)
        echo "Cleaning failed stack '$STACK' so next run can recreate fresh..."
        aws cloudformation delete-stack --stack-name "$STACK"
        aws cloudformation wait stack-delete-complete --stack-name "$STACK"
        exit 1
        ;;
      *)
        exit $rc
        ;;
    esac
  fi
}

delete_if_unrecoverable
safe_deploy
