import subprocess
import parameters
import sys
import time
import os
from tempfile import mkstemp
from shutil import move

# =======================================
#        Constants
# =======================================
ns = ""
divider = "--------------------------------------"
version = "1.0.0"

# =======================================
#        Functions
# =======================================
def setAwsProfile(profile):
    os.environ['AWS_DEFAULT_PROFILE'] = profile
    print("AWS_DEFAULT_PROFILE set to : {}".format(os.environ['AWS_DEFAULT_PROFILE']))


def parse_instance_ids(command):
    ids = {}
    p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in p.stdout.readlines():
        line = line.decode('ascii').strip().replace("\"", "").replace(",", "")
        if line not in ["[", "{", "]", "}"]:
            ids[line] = {"Username": "Administrator"}
    return ids


def parse_ip(ids, region):
    command = "aws ec2 describe-instances --instance-ids {0} --region {1} --query {2}"
    for key in ids:
        fmt_command = command.format(key, region,
                                     "\'Reservations[0].Instances[0].{PublicDnsName:PublicDnsName,PublicIpAddress:PublicIpAddress}\'")
        p = subprocess.Popen(fmt_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in p.stdout.readlines():
            line = line.decode('ascii').strip().replace("\"", "").replace(",", "")
            if line not in ["[", "{", "]", "}"]:
                tokens = line.split(": ")
                ids[key][tokens[0]] = tokens[1]

    return ids


def get_password(ids, region, pkey):
    command = "aws ec2 get-password-data --instance-id {0} --region {1} --priv-launch-key {2} --query PasswordData"
    for key in ids:
        fmt_command = command.format(key, region, pkey)
        p = subprocess.Popen(fmt_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in p.stdout.readlines():
            line = line.decode('ascii').strip().replace("\"", "").replace(",", "")
            if line not in ["[", "{", "]", "}"]:
                ids[key]["Password"] = line

    return ids


def print_instances(ids, file):
    f = open(file, "a")
    f.write("INSTANCE|PUBLIC IP|PUBLIC DNS|USERNAME|PASSWORD|ATTENDEE|ATTENDEE EMAIL|\n")
    for key in ids:
        f.write("{0}|{1}|{2}|{3}|{4}|\n".format(key, ids[key]["PublicIpAddress"],
                                                ids[key]["PublicDnsName"], ids[key]["Username"],
                                                ids[key]["Password"]))
    f.close()


def verify_input(my_input):
    if len(my_input) > 1:
        return True

    return False


def read_input(prompt):
    if sys.version_info[0] == 2:
        my_input = raw_input(prompt)
    else:
        my_input = input(prompt)

    return my_input


def usage():
    global version
    print("")
    print("python get_vm_info.py")
    print("version: {}".format(version))
    print("")
    sys.exit(0)


# =======================================
#        Main Program
# =======================================
if __name__ == "__main__":

    # Prompt and read input
    print("Generating instance report")
    scaleGroup = read_input("Enter name of Autoscale Group: ")
    while not verify_input(scaleGroup):
        scaleGroup = read_input("Autoscale Group name invalid.  Enter name of Autoscale Group: ")

    region = ""
    p = subprocess.Popen("aws configure get region", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in p.stdout.readlines():
        line = line.decode('ascii').strip().replace("\"", "").replace(",", "")
        region = line

    tmp_region = read_input("Enter region, default value [{}]: ".format(region))
    if verify_input(tmp_region):
        region = tmp_region

    key_path = read_input("Enter path to cb-day-se.pem file: ")
    while not verify_input(key_path):
        key_path = read_input("Keypath can not be blank. Enter path to cb-day-se.pem file: ")

    output_file = read_input("Enter output file: ")
    while not verify_input(output_file):
        output_file = read_input("Output file can not be blank. Enter output file: ")

    # Display inputs and confirm
    print("")
    print("Please confirm your inputs:")
    print("Autoscale Group: {}".format(scaleGroup))
    print("AWS Region: {}".format(region))
    print("Key Path: {}".format(key_path))
    print("Output File: {}".format(output_file))

    confirm = read_input("Proceed with report generation [Y/n]: ")
    while not confirm in ["Y", "n", "N"]:
        confirm = read_input("Unrecognized input [{}]. Please enter Y/n: ".format(confirm))

    # Actual Execution of AWS commands
    print("")
    print("Running report")
    instances = parse_instance_ids(
        "aws autoscaling describe-auto-scaling-groups --auto-scaling-group-name {0} --region {1} --query {2}".format(
            scaleGroup, region,
            "\'AutoScalingGroups[*].Instances[*].InstanceId\'"))

    if len(instances) > 1:
        instances = parse_ip(instances, region)
        instances = get_password(instances, region, key_path)
        print_instances(instances, output_file)
    else:
        print("Unable to find autoscale group [{}]".format(scaleGroup))

    print("Report completed")
