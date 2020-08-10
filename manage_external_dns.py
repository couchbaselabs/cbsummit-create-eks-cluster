import subprocess
import parameters
import sys
import time
import os
from tempfile import mkstemp
from shutil import move
import argparse

#=======================================
#	Constants
#=======================================
ns=""
divider="--------------------------------------"
version="1.0.0"

#=======================================
#	Variables
#=======================================

#=======================================
#	Functions
#=======================================
def setAwsProfile(profile):
	os.environ['AWS_DEFAULT_PROFILE']=profile
	print("AWS_DEFAULT_PROFILE set to : {}".format(os.environ['AWS_DEFAULT_PROFILE']))

def onError(command, retval):
	print("Error detected:: ")
	print("command: {}".format(command))
	print("retval: {}".format(retval))
	sys.exit(retval)

def execute_command(command,ignore_error):
	print(divider)
	print("Executing command : {}".format(command))
	p=subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
	for line in p.stdout.readlines():
		print(line)
	retval = p.wait()

	if retval != 0 and ignore_error == False:
		onError(command,retval)

def execute_command_with_status(command,ignore_error,status_command,status):
	print(divider)
	print("Running {}".format(command))

	execute_command(command,ignore_error)

	print("Checking completion status...")
	for x in range(parameters.ATTEMPTS):
		print("Checking attempt #{}".format(x))
		p=subprocess.Popen(status_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		for line in p.stdout.readlines():
			spaces=line.split()
			print("Status :: {}".format(spaces[0].decode('ascii')))
			if spaces[0].decode('ascii') == status:
				return 0
		retval = p.wait()
		time.sleep(parameters.WAIT_SEC)

	onError(command,retval)


def execute_command_with_return(command, ignore_error, print_output, print_command):
    results = []
    if print_command:
        print(divider)
        print("Executing command : {}".format(command))

    p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in p.stdout.readlines():
        if print_output:
            print(line)

        try:
            line = line.decode('ascii')
        except AttributeError:
            pass

        results.append(line.strip())

    retval = p.wait()

    if retval != 0 and ignore_error == False:
        on_error(command, retval)
        raise Exception("Failed to execute command and get results")
    else:
        return results

#=========================
# From EKS Tool
#=========================
def get_hosted_zone(dns):

    tmphz = execute_command_with_return(
        "aws route53 list-hosted-zones-by-name --output json --dns-name \"{0}\" --query HostedZones[0].Id".format(
            dns
        ), False, False, True)

    if len(tmphz) >= 1:
        hz_array = tmphz[0].split("/")
        hostedzone = hz_array[len(hz_array) - 1].replace("\"", "")
    else:
        hostedzone = None

    return hostedzone


def get_role_name(config_name):
    role_array = execute_command_with_return("aws iam list-roles --query Roles[].RoleName"
	, False, False, True)
    role = None

    #print("role list = {}".format(role_array))
    for i in role_array:
        #print("Checking {}-NodeInstanceRole".format(config_name))
        if "{}-NodeInstanceRole".format(config_name) in i:
            role = i.replace(",", "")

    return role


def get_pol_arn():
    pol_arn_array = execute_command_with_return(
        "aws iam list-policies --query 'Policies[?PolicyName==`ExternalDNS`].Arn'"
        , False, False, True)

    pol_arn = None
    if len(pol_arn_array) > 1:
        pol_arn = pol_arn_array[1]

    return pol_arn


def usage():
	global version
	sys.exit(0)


def attach_external_dns():
    hostedzone = get_hosted_zone(parameters.DNS)
    role = get_role_name(parameters.EKS_NODES_STACK_NAME)
    policy_arn = get_pol_arn()

    if hostedzone is not None and role is not None and policy_arn is not None:
        execute_command("aws iam attach-role-policy --role-name {0} --policy-arn {1}".format(
            role, policy_arn), False)

        return True
    else:
        return False


def detach_external_dns():
    role = get_role_name(parameters.EKS_NODES_STACK_NAME)

    pol_arn = get_pol_arn()

    if role is not None and pol_arn is not None:
        execute_command("aws iam detach-role-policy --role-name {0} --policy-arn {1}".format(
            role, pol_arn), True)
	

#=======================================
#	Main Program
#=======================================
if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('mode', help="Enter the mode to run this script [attach | detach ]")
    parser.add_argument("-p", "--profile", help="Specify the AWS profile to use")
    args = parser.parse_args()

    if args.profile is not None:
	setAwsProfile(args.profile)

    if args.mode.lower() == "attach":
        print("Enabling ExternalDNS")
        attach_external_dns()
    elif args.mode.lower() == "detach":
        print("Disabling ExternalDNS")
        detach_external_dns()
    else:
        print("Unknown mode {}".format(args.mode))

	
