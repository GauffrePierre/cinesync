// Dictionnaire anglais : une partie par zone de l'application, fusionnées ici.
import common from './common'
import discover from './discover'
import detail from './detail'
import profile from './profile'
import shell from './shell'
import admin from './admin'
import auth from './auth'
import newsDict from './news'

export default { ...common, ...discover, ...detail, ...profile, ...admin, ...auth, ...newsDict, ...shell }
