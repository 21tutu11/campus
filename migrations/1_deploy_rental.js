const CampusRental = artifacts.require("CampusRental");
module.exports = function(deployer) {
  deployer.deploy(CampusRental);
};